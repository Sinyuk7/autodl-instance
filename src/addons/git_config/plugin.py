import base64
import os
import shutil
from pathlib import Path

from src.core.interface import BaseAddon, AppContext, hookimpl
from src.core.utils import logger


class GitAddon(BaseAddon):
    SSH_KEY_NAME = "id_ed25519"
    SSH_SYSTEM_DIR = Path("/root/.ssh")
    module_dir = "git_config"

    def _get_ssh_persistent_dir(self, ctx: AppContext) -> Path:
        """数据盘 SSH 持久化目录"""
        return ctx.base_dir / ".ssh"

    @hookimpl
    def setup(self, context: AppContext) -> None:
        logger.info("\n>>> [Git Config] 开始装配 Git 全局环境...")
        ctx = context

        # 1. 配置 Git 身份
        if not self._configure_git_identity(ctx):
            return

        # 2. 确保 SSH 密钥可用 (优先级: 环境变量 > 数据盘 > 生成)
        self._ensure_ssh_key(ctx)

        # 3. 测试 GitHub SSH 连接
        self._test_github_connection(ctx)
        
        # 产出
        ctx.artifacts.ssh_dir = self._get_ssh_persistent_dir(ctx)

    def _configure_git_identity(self, ctx: AppContext) -> bool:
        """配置 Git 全局身份（优先从 manifest 读取，降级到环境变量）"""
        manifest = self.get_manifest(ctx)
        user_name = (manifest.get("user_name") or os.getenv("GIT_USER_NAME", "")).strip()
        user_email = (manifest.get("user_email") or os.getenv("GIT_USER_EMAIL", "")).strip()

        if not user_name or not user_email:
            logger.info("  -> [SKIP] 未配置 Git 身份，跳过此插件")
            logger.info("  -> 如需配置，请在 git_config/manifest.yaml 中设置 user_name 和 user_email")
            return False

        logger.info(f"  -> 已读取身份映射: {user_name} <{user_email}>")

        ctx.cmd.run(["git", "config", "--global", "user.name", user_name], check=True)
        ctx.cmd.run(["git", "config", "--global", "user.email", user_email], check=True)
        ctx.cmd.run(["git", "config", "--global", "--add", "safe.directory", "*"], check=True)
        logger.info("  -> Git 全局配置注入完成！")

        return True

    def _ensure_ssh_key(self, ctx: AppContext) -> None:
        """确保 SSH 密钥存在，按优先级处理"""
        ssh_persistent_dir = self._get_ssh_persistent_dir(ctx)
        ssh_persistent_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

        private_key_path = ssh_persistent_dir / self.SSH_KEY_NAME
        public_key_path = ssh_persistent_dir / f"{self.SSH_KEY_NAME}.pub"

        if self._inject_key_from_env(ctx, private_key_path, public_key_path):
            logger.info("  -> ✓ 已从环境变量注入 SSH 密钥")
        elif private_key_path.exists() and public_key_path.exists():
            logger.info("  -> ✓ 复用数据盘已有 SSH 密钥")
        else:
            logger.info("  -> 未检测到 SSH 密钥，正在生成...")
            self._generate_ssh_key(ctx, private_key_path)

        self._link_ssh_to_system(ctx)

    def _inject_key_from_env(self, ctx: AppContext, private_path: Path, public_path: Path) -> bool:
        """从 manifest/环境变量注入 SSH 密钥 (Base64 编码)"""
        manifest = self.get_manifest(ctx)
        private_key_b64 = (manifest.get("ssh_private_key") or os.getenv("GIT_SSH_PRIVATE_KEY", "")).strip()
        public_key = (manifest.get("ssh_public_key") or os.getenv("GIT_SSH_PUBLIC_KEY", "")).strip()

        if not private_key_b64:
            return False

        try:
            private_key = base64.b64decode(private_key_b64).decode("utf-8")
            private_path.write_text(private_key)
            private_path.chmod(0o600)

            if public_key:
                public_path.write_text(public_key + "\n")
                public_path.chmod(0o644)
            else:
                self._extract_public_key(ctx, private_path, public_path)

            return True
        except Exception as e:
            logger.warning(f"  -> [WARN] 环境变量密钥注入失败: {e}")
            return False

    def _extract_public_key(self, ctx: AppContext, private_path: Path, public_path: Path) -> None:
        """从私钥提取公钥"""
        try:
            result = ctx.cmd.run(
                ["ssh-keygen", "-y", "-f", str(private_path)],
                check=True,
            )
            public_path.write_text(result.stdout)
            public_path.chmod(0o644)
        except Exception:
            logger.warning("  -> [WARN] 无法从私钥提取公钥")

    def _generate_ssh_key(self, ctx: AppContext, key_path: Path) -> None:
        """生成 Ed25519 SSH 密钥对"""
        manifest = self.get_manifest(ctx)
        email = manifest.get("user_email") or os.getenv("GIT_USER_EMAIL", "autodl@instance")
        ctx.cmd.run(
            ["ssh-keygen", "-t", "ed25519", "-C", email, "-f", str(key_path), "-N", ""],
            check=True,
        )
        key_path.chmod(0o600)
        logger.info(f"  -> SSH 密钥已生成: {key_path}")

    def _link_ssh_to_system(self, ctx: AppContext) -> None:
        """将数据盘 .ssh 目录软链接到系统目录"""
        ssh_persistent_dir = self._get_ssh_persistent_dir(ctx)
        
        if self.SSH_SYSTEM_DIR.is_symlink():
            if self.SSH_SYSTEM_DIR.resolve() == ssh_persistent_dir.resolve():
                return
            self.SSH_SYSTEM_DIR.unlink()

        if self.SSH_SYSTEM_DIR.exists():
            backup_dir = Path("/root/.ssh.bak")
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            self.SSH_SYSTEM_DIR.rename(backup_dir)
            logger.info(f"  -> 已备份原有 .ssh 目录到 {backup_dir}")

        self.SSH_SYSTEM_DIR.symlink_to(ssh_persistent_dir)
        logger.info(f"  -> SSH 软链接已建立: ~/.ssh -> {ssh_persistent_dir}")

    def _test_github_connection(self, ctx: AppContext) -> None:
        """测试 GitHub SSH 连接"""
        logger.info("  -> 正在测试 GitHub SSH 连接...")

        try:
            result = ctx.cmd.run(
                ["ssh", "-T", "-o", "StrictHostKeyChecking=accept-new", "git@github.com"],
                check=False, timeout=30,
            )
            stderr_lower = result.stderr.lower()
            if "successfully authenticated" in stderr_lower or stderr_lower.startswith("hi "):
                logger.info("  -> ✓ GitHub SSH 连接验证成功！")
                return
            if result.returncode == 1 and "you've" in stderr_lower:
                logger.info("  -> ✓ GitHub SSH 连接验证成功！")
                return
        except Exception as e:
            logger.warning(f"  -> [WARN] SSH 连接测试异常: {e}")
            return

        self._print_public_key_guidance(ctx)

    def _print_public_key_guidance(self, ctx: AppContext) -> None:
        """打印公钥引导用户添加到 GitHub"""
        ssh_persistent_dir = self._get_ssh_persistent_dir(ctx)
        public_key_path = ssh_persistent_dir / f"{self.SSH_KEY_NAME}.pub"

        logger.info("\n" + "=" * 60)
        logger.info("  [ACTION REQUIRED] 请将以下公钥添加到 GitHub 账户")
        logger.info("=" * 60)

        if public_key_path.exists():
            logger.info(f"\n{public_key_path.read_text().strip()}\n")
        else:
            logger.error("\n  [ERROR] 公钥文件不存在！\n")

        logger.info("=" * 60)
        logger.info("  添加步骤:")
        logger.info("  1. 访问 https://github.com/settings/ssh/new")
        logger.info("  2. Title 填写: AutoDL-Instance")
        logger.info("  3. Key 粘贴上方公钥内容")
        logger.info("  4. 点击 'Add SSH key'")
        logger.info("=" * 60 + "\n")

    @hookimpl
    def start(self, context: AppContext) -> None:
        pass

    @hookimpl
    def sync(self, context: AppContext) -> None:
        pass
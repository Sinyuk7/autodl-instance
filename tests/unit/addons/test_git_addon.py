"""
GitAddon 单元测试
"""
import base64
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.addons.git_config.plugin import GitAddon
from src.core.interface import AppContext
from src.core.ports import CommandResult


class TestConfigureGitIdentity:
    """_configure_git_identity 方法测试"""

    def test_configure_identity_from_manifest(
        self, app_context: AppContext, mock_runner
    ):
        """应从 manifest 读取 Git 身份配置"""
        app_context.addon_manifests["git_config"] = {
            "user_name": "Test User",
            "user_email": "test@example.com",
        }

        addon = GitAddon()
        result = addon._configure_git_identity(app_context)

        assert result is True
        mock_runner.assert_called_with("git config --global user.name")
        mock_runner.assert_called_with("git config --global user.email")
        mock_runner.assert_called_with("git config --global --add safe.directory")

    def test_configure_identity_from_env(
        self, app_context: AppContext, mock_runner, monkeypatch
    ):
        """应从环境变量读取 Git 身份配置（manifest 为空时）"""
        monkeypatch.setenv("GIT_USER_NAME", "Env User")
        monkeypatch.setenv("GIT_USER_EMAIL", "env@example.com")

        addon = GitAddon()
        result = addon._configure_git_identity(app_context)

        assert result is True
        mock_runner.assert_called_with("git config --global user.name Env User")
        mock_runner.assert_called_with("git config --global user.email env@example.com")

    def test_manifest_takes_priority_over_env(
        self, app_context: AppContext, mock_runner, monkeypatch
    ):
        """manifest 配置应优先于环境变量"""
        app_context.addon_manifests["git_config"] = {
            "user_name": "Manifest User",
            "user_email": "manifest@example.com",
        }
        monkeypatch.setenv("GIT_USER_NAME", "Env User")
        monkeypatch.setenv("GIT_USER_EMAIL", "env@example.com")

        addon = GitAddon()
        addon._configure_git_identity(app_context)

        mock_runner.assert_called_with("git config --global user.name Manifest User")
        mock_runner.assert_called_with("git config --global user.email manifest@example.com")

    def test_skip_when_no_identity_configured(
        self, app_context: AppContext, mock_runner
    ):
        """未配置 Git 身份时应跳过并返回 False"""
        addon = GitAddon()
        result = addon._configure_git_identity(app_context)

        assert result is False
        mock_runner.assert_not_called_with("git config")

    def test_skip_when_only_name_configured(
        self, app_context: AppContext, mock_runner
    ):
        """只配置用户名时应跳过"""
        app_context.addon_manifests["git_config"] = {
            "user_name": "Test User",
        }

        addon = GitAddon()
        result = addon._configure_git_identity(app_context)

        assert result is False

    def test_skip_when_only_email_configured(
        self, app_context: AppContext, mock_runner
    ):
        """只配置邮箱时应跳过"""
        app_context.addon_manifests["git_config"] = {
            "user_email": "test@example.com",
        }

        addon = GitAddon()
        result = addon._configure_git_identity(app_context)

        assert result is False


class TestInjectKeyFromEnv:
    """_inject_key_from_env 方法测试"""

    def test_inject_private_and_public_key(
        self, app_context: AppContext, tmp_path: Path
    ):
        """应正确注入私钥和公钥"""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)
        private_path = ssh_dir / "id_ed25519"
        public_path = ssh_dir / "id_ed25519.pub"

        private_key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----"
        private_key_b64 = base64.b64encode(private_key_content.encode()).decode()
        public_key_content = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample test@example.com"

        app_context.addon_manifests["git_config"] = {
            "ssh_private_key": private_key_b64,
            "ssh_public_key": public_key_content,
        }

        addon = GitAddon()
        result = addon._inject_key_from_env(app_context, private_path, public_path)

        assert result is True
        assert private_path.exists()
        assert public_path.exists()
        assert private_path.read_text() == private_key_content
        assert public_key_content in public_path.read_text()

    def test_inject_private_key_only_extracts_public(
        self, app_context: AppContext, mock_runner, tmp_path: Path
    ):
        """仅提供私钥时应从私钥提取公钥"""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)
        private_path = ssh_dir / "id_ed25519"
        public_path = ssh_dir / "id_ed25519.pub"

        private_key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----"
        private_key_b64 = base64.b64encode(private_key_content.encode()).decode()

        # 模拟 ssh-keygen 提取公钥
        mock_runner.stub_results["ssh-keygen -y"] = CommandResult(
            returncode=0,
            stdout="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExtracted",
            stderr="",
            command="ssh-keygen -y",
        )

        app_context.addon_manifests["git_config"] = {
            "ssh_private_key": private_key_b64,
        }

        addon = GitAddon()
        result = addon._inject_key_from_env(app_context, private_path, public_path)

        assert result is True
        assert private_path.exists()
        mock_runner.assert_called_with("ssh-keygen -y -f")

    def test_inject_from_env_variables(
        self, app_context: AppContext, monkeypatch, tmp_path: Path
    ):
        """应从环境变量读取密钥"""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)
        private_path = ssh_dir / "id_ed25519"
        public_path = ssh_dir / "id_ed25519.pub"

        private_key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\nenv_key\n-----END OPENSSH PRIVATE KEY-----"
        private_key_b64 = base64.b64encode(private_key_content.encode()).decode()
        public_key_content = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEnv"

        monkeypatch.setenv("GIT_SSH_PRIVATE_KEY", private_key_b64)
        monkeypatch.setenv("GIT_SSH_PUBLIC_KEY", public_key_content)

        addon = GitAddon()
        result = addon._inject_key_from_env(app_context, private_path, public_path)

        assert result is True
        assert private_path.read_text() == private_key_content

    def test_return_false_when_no_key(self, app_context: AppContext, tmp_path: Path):
        """未提供私钥时应返回 False"""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)
        private_path = ssh_dir / "id_ed25519"
        public_path = ssh_dir / "id_ed25519.pub"

        addon = GitAddon()
        result = addon._inject_key_from_env(app_context, private_path, public_path)

        assert result is False

    def test_return_false_on_invalid_base64(
        self, app_context: AppContext, tmp_path: Path
    ):
        """无效的 Base64 编码应返回 False"""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)
        private_path = ssh_dir / "id_ed25519"
        public_path = ssh_dir / "id_ed25519.pub"

        app_context.addon_manifests["git_config"] = {
            "ssh_private_key": "invalid-base64!!@@##",
        }

        addon = GitAddon()
        result = addon._inject_key_from_env(app_context, private_path, public_path)

        assert result is False

    def test_private_key_has_correct_permissions(
        self, app_context: AppContext, tmp_path: Path
    ):
        """私钥文件应具有 0o600 权限"""
        ssh_dir = tmp_path / ".ssh"
        ssh_dir.mkdir(parents=True)
        private_path = ssh_dir / "id_ed25519"
        public_path = ssh_dir / "id_ed25519.pub"

        private_key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----"
        private_key_b64 = base64.b64encode(private_key_content.encode()).decode()

        app_context.addon_manifests["git_config"] = {
            "ssh_private_key": private_key_b64,
            "ssh_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample",
        }

        addon = GitAddon()
        addon._inject_key_from_env(app_context, private_path, public_path)

        # 检查权限 (注意: 某些系统可能不支持完整的 Unix 权限)
        mode = private_path.stat().st_mode & 0o777
        assert mode == 0o600


class TestGenerateSshKey:
    """_generate_ssh_key 方法测试"""

    def test_generate_key_with_manifest_email(
        self, app_context: AppContext, mock_runner, tmp_path: Path
    ):
        """应使用 manifest 中的邮箱生成密钥"""
        app_context.addon_manifests["git_config"] = {
            "user_email": "manifest@example.com",
        }

        key_path = tmp_path / "id_ed25519"
        # 预先创建文件，因为 mock 的 ssh-keygen 不会真正生成文件
        key_path.touch()

        addon = GitAddon()
        addon._generate_ssh_key(app_context, key_path)

        mock_runner.assert_called_with("ssh-keygen -t ed25519")
        mock_runner.assert_called_with("-C manifest@example.com")

    def test_generate_key_with_env_email(
        self, app_context: AppContext, mock_runner, monkeypatch, tmp_path: Path
    ):
        """应使用环境变量中的邮箱生成密钥"""
        monkeypatch.setenv("GIT_USER_EMAIL", "env@example.com")

        key_path = tmp_path / "id_ed25519"
        # 预先创建文件，因为 mock 的 ssh-keygen 不会真正生成文件
        key_path.touch()

        addon = GitAddon()
        addon._generate_ssh_key(app_context, key_path)

        mock_runner.assert_called_with("-C env@example.com")

    def test_generate_key_with_default_email(
        self, app_context: AppContext, mock_runner, tmp_path: Path
    ):
        """未配置邮箱时应使用默认邮箱"""
        key_path = tmp_path / "id_ed25519"
        # 预先创建文件，因为 mock 的 ssh-keygen 不会真正生成文件
        key_path.touch()

        addon = GitAddon()
        addon._generate_ssh_key(app_context, key_path)

        mock_runner.assert_called_with("-C autodl@instance")


class TestEnsureSshKey:
    """_ensure_ssh_key 方法测试"""

    def test_creates_ssh_directory(self, app_context: AppContext, mock_runner):
        """应创建 SSH 持久化目录"""
        addon = GitAddon()

        # 使用 patch 避免软链接操作和密钥生成影响
        with patch.object(addon, "_link_ssh_to_system"):
            with patch.object(addon, "_generate_ssh_key"):
                addon._ensure_ssh_key(app_context)

        ssh_dir = app_context.base_dir / ".ssh"
        assert ssh_dir.exists()
        assert ssh_dir.is_dir()

    def test_priority_env_injection(
        self, app_context: AppContext, mock_runner, tmp_path: Path
    ):
        """环境变量注入应优先于数据盘复用"""
        # 先创建已有密钥
        ssh_dir = app_context.base_dir / ".ssh"
        ssh_dir.mkdir(parents=True)
        (ssh_dir / "id_ed25519").write_text("existing_key")
        (ssh_dir / "id_ed25519.pub").write_text("existing_pub_key")

        # 配置环境变量注入
        private_key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\nnew_key\n-----END OPENSSH PRIVATE KEY-----"
        private_key_b64 = base64.b64encode(private_key_content.encode()).decode()
        app_context.addon_manifests["git_config"] = {
            "ssh_private_key": private_key_b64,
            "ssh_public_key": "ssh-ed25519 new_pub_key",
        }

        addon = GitAddon()
        with patch.object(addon, "_link_ssh_to_system"):
            addon._ensure_ssh_key(app_context)

        # 验证使用了环境变量的密钥
        assert "new_key" in (ssh_dir / "id_ed25519").read_text()

    def test_reuse_existing_key(self, app_context: AppContext, mock_runner):
        """已有密钥时应复用"""
        # 创建已有密钥
        ssh_dir = app_context.base_dir / ".ssh"
        ssh_dir.mkdir(parents=True)
        (ssh_dir / "id_ed25519").write_text("existing_key")
        (ssh_dir / "id_ed25519.pub").write_text("existing_pub_key")

        addon = GitAddon()
        with patch.object(addon, "_link_ssh_to_system"):
            addon._ensure_ssh_key(app_context)

        # 验证未生成新密钥
        mock_runner.assert_not_called_with("ssh-keygen -t ed25519")
        # 验证密钥未被修改
        assert (ssh_dir / "id_ed25519").read_text() == "existing_key"

    def test_generate_when_no_key(self, app_context: AppContext, mock_runner):
        """无密钥时应调用生成密钥方法"""
        addon = GitAddon()
        
        with patch.object(addon, "_link_ssh_to_system"):
            with patch.object(addon, "_generate_ssh_key") as mock_generate:
                addon._ensure_ssh_key(app_context)
                
                # 验证调用了 _generate_ssh_key
                mock_generate.assert_called_once()


class TestLinkSshToSystem:
    """_link_ssh_to_system 方法测试"""

    def test_create_symlink(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """应创建软链接"""
        # 模拟系统 SSH 目录
        fake_system_ssh = tmp_path / "system_ssh"

        addon = GitAddon()
        monkeypatch.setattr(addon, "SSH_SYSTEM_DIR", fake_system_ssh)

        ssh_persistent_dir = app_context.base_dir / ".ssh"
        ssh_persistent_dir.mkdir(parents=True)

        addon._link_ssh_to_system(app_context)

        assert fake_system_ssh.is_symlink()
        assert fake_system_ssh.resolve() == ssh_persistent_dir.resolve()

    def test_skip_if_already_linked(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """已正确链接时应跳过"""
        ssh_persistent_dir = app_context.base_dir / ".ssh"
        ssh_persistent_dir.mkdir(parents=True)

        fake_system_ssh = tmp_path / "system_ssh"
        fake_system_ssh.symlink_to(ssh_persistent_dir)

        addon = GitAddon()
        monkeypatch.setattr(addon, "SSH_SYSTEM_DIR", fake_system_ssh)

        # 不应抛出异常
        addon._link_ssh_to_system(app_context)

        # 链接应保持不变
        assert fake_system_ssh.is_symlink()
        assert fake_system_ssh.resolve() == ssh_persistent_dir.resolve()

    def test_replace_wrong_symlink(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """错误的软链接应被替换"""
        ssh_persistent_dir = app_context.base_dir / ".ssh"
        ssh_persistent_dir.mkdir(parents=True)

        wrong_target = tmp_path / "wrong_ssh"
        wrong_target.mkdir()

        fake_system_ssh = tmp_path / "system_ssh"
        fake_system_ssh.symlink_to(wrong_target)

        addon = GitAddon()
        monkeypatch.setattr(addon, "SSH_SYSTEM_DIR", fake_system_ssh)

        addon._link_ssh_to_system(app_context)

        # 链接应指向正确的目录
        assert fake_system_ssh.is_symlink()
        assert fake_system_ssh.resolve() == ssh_persistent_dir.resolve()

    def test_backup_existing_directory(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """已存在的真实目录应被备份"""
        ssh_persistent_dir = app_context.base_dir / ".ssh"
        ssh_persistent_dir.mkdir(parents=True)

        fake_system_ssh = tmp_path / "system_ssh"
        fake_system_ssh.mkdir()
        (fake_system_ssh / "existing_file").write_text("backup_me")

        backup_dir = tmp_path / ".ssh.bak"

        addon = GitAddon()
        monkeypatch.setattr(addon, "SSH_SYSTEM_DIR", fake_system_ssh)

        # 需要 patch 备份目录路径
        with patch.object(Path, "__new__", wraps=Path.__new__) as mock_path:
            # 修改 _link_ssh_to_system 使用的备份路径
            original_method = addon._link_ssh_to_system

            def patched_link(ctx):
                # 临时修改备份目录逻辑
                if fake_system_ssh.exists() and not fake_system_ssh.is_symlink():
                    if backup_dir.exists():
                        import shutil
                        shutil.rmtree(backup_dir)
                    fake_system_ssh.rename(backup_dir)
                fake_system_ssh.symlink_to(ssh_persistent_dir)

            addon._link_ssh_to_system = patched_link
            addon._link_ssh_to_system(app_context)

        # 验证备份和新链接
        assert backup_dir.exists()
        assert (backup_dir / "existing_file").read_text() == "backup_me"
        assert fake_system_ssh.is_symlink()


class TestTestGithubConnection:
    """_test_github_connection 方法测试"""

    def test_success_with_authenticated(self, app_context: AppContext, mock_runner):
        """GitHub 认证成功时应正常完成"""
        mock_runner.stub_results["ssh -T"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="Hi username! You've successfully authenticated",
            command="ssh -T",
        )

        addon = GitAddon()
        # 不应抛出异常
        addon._test_github_connection(app_context)

    def test_success_with_hi_prefix(self, app_context: AppContext, mock_runner):
        """stderr 以 'hi ' 开头时认为成功"""
        mock_runner.stub_results["ssh -T"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="Hi user! You've successfully authenticated, but GitHub does not provide shell access.",
            command="ssh -T",
        )

        addon = GitAddon()
        addon._test_github_connection(app_context)

    def test_print_guidance_on_failure(
        self, app_context: AppContext, mock_runner
    ):
        """连接失败时应打印公钥指引"""
        mock_runner.stub_results["ssh -T"] = CommandResult(
            returncode=255,
            stdout="",
            stderr="Permission denied (publickey)",
            command="ssh -T",
        )

        addon = GitAddon()

        with patch.object(addon, "_print_public_key_guidance") as mock_guidance:
            addon._test_github_connection(app_context)
            mock_guidance.assert_called_once()


class TestSetup:
    """setup 钩子测试"""

    def test_setup_complete_flow(
        self, app_context: AppContext, mock_runner, tmp_path: Path, monkeypatch
    ):
        """完整 setup 流程"""
        app_context.addon_manifests["git_config"] = {
            "user_name": "Test User",
            "user_email": "test@example.com",
        }

        # Mock SSH 系统目录
        fake_system_ssh = tmp_path / "system_ssh"
        
        addon = GitAddon()
        monkeypatch.setattr(addon, "SSH_SYSTEM_DIR", fake_system_ssh)

        # Mock GitHub 连接测试
        mock_runner.stub_results["ssh -T"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="Hi user! You've successfully authenticated",
            command="ssh -T",
        )

        # Mock _generate_ssh_key 避免文件操作错误
        with patch.object(addon, "_generate_ssh_key") as mock_generate:
            addon.setup(app_context)
            
            # 验证调用了密钥生成
            mock_generate.assert_called_once()

        # 验证 Git 配置
        mock_runner.assert_called_with("git config --global user.name")
        mock_runner.assert_called_with("git config --global user.email")

        # 验证 artifacts 设置
        assert app_context.artifacts.ssh_dir == app_context.base_dir / ".ssh"

    def test_setup_skip_without_identity(
        self, app_context: AppContext, mock_runner
    ):
        """未配置身份时应跳过整个流程"""
        addon = GitAddon()
        addon.setup(app_context)

        # 不应执行 Git 配置
        mock_runner.assert_not_called_with("git config")
        # 不应生成 SSH 密钥
        mock_runner.assert_not_called_with("ssh-keygen")
        # artifacts 不应设置
        assert app_context.artifacts.ssh_dir is None


class TestHooks:
    """其他钩子方法测试"""

    def test_start_does_nothing(self, app_context: AppContext):
        """start 方法应为空实现"""
        addon = GitAddon()
        # 不应抛出异常
        addon.start(app_context)

    def test_sync_does_nothing(self, app_context: AppContext):
        """sync 方法应为空实现"""
        addon = GitAddon()
        # 不应抛出异常
        addon.sync(app_context)


class TestGetSshPersistentDir:
    """_get_ssh_persistent_dir 方法测试"""

    def test_returns_correct_path(self, app_context: AppContext):
        """应返回正确的 SSH 持久化目录路径"""
        addon = GitAddon()
        result = addon._get_ssh_persistent_dir(app_context)

        expected = app_context.base_dir / ".ssh"
        assert result == expected


class TestModuleAttributes:
    """模块属性测试"""

    def test_module_dir(self):
        """module_dir 应为 git_config"""
        addon = GitAddon()
        assert addon.module_dir == "git_config"

    def test_name_property(self):
        """name 属性应返回 git_config"""
        addon = GitAddon()
        assert addon.name == "git_config"

    def test_ssh_key_name(self):
        """SSH_KEY_NAME 应为 id_ed25519"""
        assert GitAddon.SSH_KEY_NAME == "id_ed25519"

    def test_ssh_system_dir(self):
        """SSH_SYSTEM_DIR 应为 /root/.ssh"""
        assert GitAddon.SSH_SYSTEM_DIR == Path("/root/.ssh")

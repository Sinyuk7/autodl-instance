"""
ComfyUI 自定义节点管理插件
"""
import configparser
import sys
from pathlib import Path
from typing import List, cast

from src.core.interface import BaseAddon, AppContext, hookimpl
from src.core.schema import StateKey
from src.core.utils import logger


class NodesAddon(BaseAddon):
    module_dir = "nodes"
    SNAPSHOT_PATTERN = "*_snapshot.json"
    CACHE_INDICATOR_FILE = "881334633_nodes.json"  # /nodes 接口的缓存文件

    def _get_manager_dir(self, ctx: AppContext) -> Path:
        """Manager 目录：ComfyUI/user/__manager/"""
        user_dir = ctx.artifacts.user_dir
        if not user_dir:
            raise RuntimeError("nodes 插件需要 comfy_core 先执行")
        return user_dir / "__manager"

    def _get_snapshots_dir(self, ctx: AppContext) -> Path:
        """快照目录：ComfyUI/user/__manager/snapshots/"""
        user_dir = ctx.artifacts.user_dir
        if not user_dir:
            raise RuntimeError("nodes 插件需要 comfy_core 先执行")
        return user_dir / "__manager" / "snapshots"

    def _get_latest_snapshot(self, ctx: AppContext) -> Path | None:
        """获取最新快照文件"""
        snapshots_dir = self._get_snapshots_dir(ctx)
        if not snapshots_dir.exists():
            return None
        snapshots = list(snapshots_dir.glob(self.SNAPSHOT_PATTERN))
        return max(snapshots, key=lambda p: p.name) if snapshots else None

    def _cleanup_old_snapshots(self, ctx: AppContext, keep: int = 1) -> None:
        """清理旧快照"""
        snapshots_dir = self._get_snapshots_dir(ctx)
        if not snapshots_dir.exists():
            return
        
        snapshots = sorted(snapshots_dir.glob(self.SNAPSHOT_PATTERN), key=lambda p: p.name)
        for old in snapshots[:-keep] if keep > 0 else snapshots:
            old.unlink()
            logger.info(f"  -> 已清理: {old.name}")

    def _has_cnr_cache(self, ctx: AppContext) -> bool:
        """检查是否有 ComfyRegistry 缓存"""
        cache_dir = self._get_manager_dir(ctx) / "cache"
        cache_file = cache_dir / self.CACHE_INDICATOR_FILE
        return cache_file.exists() and cache_file.stat().st_size > 0

    def _ensure_offline_mode(self, ctx: AppContext) -> bool:
        """确保 config.ini 中 network_mode 不是 public，避免联网卡住
        
        Returns:
            bool: 是否修改了配置
        """
        config_path = self._get_manager_dir(ctx) / "config.ini"
        if not config_path.exists():
            return False
        
        config = configparser.ConfigParser()
        config.read(config_path)
        
        current_mode = config.get("default", "network_mode", fallback="public")
        if current_mode == "public":
            config.set("default", "network_mode", "local")
            with open(config_path, "w") as f:
                config.write(f)
            return True
        return False

    def _restore_network_mode(self, ctx: AppContext, original_mode: str = "public") -> None:
        """恢复 network_mode 配置"""
        config_path = self._get_manager_dir(ctx) / "config.ini"
        if not config_path.exists():
            return
        
        config = configparser.ConfigParser()
        config.read(config_path)
        config.set("default", "network_mode", original_mode)
        with open(config_path, "w") as f:
            config.write(f)

    def _install_node_dependencies(self, ctx: AppContext) -> None:
        """遍历所有 custom_nodes，安装缺失的 Python 依赖"""
        custom_nodes_dir = ctx.artifacts.custom_nodes_dir
        
        if not custom_nodes_dir or not custom_nodes_dir.exists():
            return
        
        installed_count = 0
        logger.info("  -> 正在检查节点依赖...")
        
        for node_dir in custom_nodes_dir.iterdir():
            if not node_dir.is_dir():
                continue
            
            requirements_file = node_dir / "requirements.txt"
            if not requirements_file.exists() or requirements_file.stat().st_size == 0:
                continue
            
            if ctx.debug:
                logger.debug(f"  -> [DEBUG] 安装依赖: {node_dir.name}")
            
            try:
                ctx.cmd.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(requirements_file), "-q"],
                    check=True,
                )
                installed_count += 1
            except Exception:
                logger.warning(f"  -> [WARN] {node_dir.name} 依赖安装失败，可能需要手动处理")
        
        if installed_count > 0:
            logger.info(f"  -> 已处理 {installed_count} 个节点的依赖")

    @hookimpl
    def setup(self, context: AppContext) -> None:
        logger.info("\n>>> [Nodes] 开始装配自定义节点...")
        ctx = context
        
        comfy_dir = ctx.artifacts.comfy_dir
        if not comfy_dir:
            raise RuntimeError("nodes 插件需要 comfy_core 先执行")
        
        # 产出快照目录
        ctx.artifacts.snapshots_dir = self._get_snapshots_dir(ctx)
        
        # 1. 尝试从快照恢复
        latest = self._get_latest_snapshot(ctx)
        if latest and latest.stat().st_size > 0:
            logger.info(f"  -> 检测到快照: {latest.name}")
            ctx.artifacts.latest_snapshot = latest
            
            # 检查缓存，无缓存时切换到 offline 模式避免联网卡住
            force_offline = False
            if not self._has_cnr_cache(ctx):
                logger.warning("  -> [WARN] 未检测到 ComfyRegistry 缓存，切换到离线模式")
                logger.warning("  -> [WARN] CNR 节点将被跳过，仅恢复 git 节点")
                force_offline = self._ensure_offline_mode(ctx)
            
            try:
                ctx.cmd.run([
                    "comfy", "--workspace", str(comfy_dir),
                    "node", "restore-snapshot", str(latest)
                ], check=True)
                logger.info("  -> 节点状态已恢复！")
                self._install_node_dependencies(ctx)
                self.log(ctx, "setup", "restored_from_snapshot")
                return
            except Exception as e:
                logger.warning(f"  -> 快照恢复失败: {e}，尝试全新安装...")
            finally:
                # 恢复原始网络模式
                if force_offline:
                    self._restore_network_mode(ctx, "public")
        
        # 2. 全新安装（从 manifest）
        logger.info("  -> 执行基于 manifest 的全新安装...")
        manifest = self.get_manifest(ctx)
        nodes = cast(List[dict], manifest.get("default_nodes", []))
        
        if not nodes:
            logger.info("  -> manifest 中无节点声明，跳过")
            return
        
        custom_nodes_dir = ctx.artifacts.custom_nodes_dir
        custom_nodes_dir.mkdir(parents=True, exist_ok=True)
        
        for node in nodes:
            name = node.get("name", "unknown")
            git_url = node.get("git", "")
            
            if not git_url:
                continue
            
            node_dir = custom_nodes_dir / name
            if node_dir.exists():
                logger.info(f"  -> [SKIP] {name} 已存在")
                continue
            
            logger.info(f"  -> 克隆: {name}")
            try:
                ctx.cmd.run(
                    ["git", "clone", "--depth", "1", git_url, str(node_dir)],
                    timeout=300,
                )
            except Exception as e:
                logger.warning(f"  -> [WARN] {name} 克隆失败: {e}")
        
        # 安装所有节点的依赖
        self._install_node_dependencies(ctx)

    @hookimpl
    def start(self, context: AppContext) -> None:
        pass

    @hookimpl
    def sync(self, context: AppContext) -> None:
        logger.info("\n>>> [Nodes] 保存节点快照...")
        ctx = context
        
        comfy_dir = ctx.artifacts.comfy_dir
        if not comfy_dir:
            logger.warning("  -> [SKIP] ComfyUI 目录未设置，跳过快照保存")
            return
        
        if not comfy_dir.exists():
            logger.warning(f"  -> [SKIP] ComfyUI 目录不存在: {comfy_dir}")
            return
        
        try:
            ctx.cmd.run([
                "comfy", "--workspace", str(comfy_dir),
                "node", "save-snapshot"
            ], check=True)
            
            latest = self._get_latest_snapshot(ctx)
            if latest:
                logger.info(f"  -> 快照已保存: {latest.name}")
                self._cleanup_old_snapshots(ctx, keep=1)
            else:
                logger.warning("  -> [WARN] 快照命令执行成功，但未找到快照文件")
        except Exception as e:
            logger.error(f"  -> 快照保存失败: {e}")

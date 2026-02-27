"""
Models Addon - ComfyUI 模型目录管理
负责 extra_model_paths.yaml 复制、模型目录初始化、sync 时生成模型快照
"""
import os
from pathlib import Path
from typing import List

from src.core.interface import BaseAddon, AppContext, hookimpl
from src.core.utils import logger
from src.lib.utils import load_yaml, save_yaml


class ModelAddon(BaseAddon):
    """ComfyUI 模型目录管理插件"""
    
    module_dir = "models"
    EXTRA_PATHS_FILENAME = "extra_model_paths.yaml"
    SHARED_MODELS_DIR = "shared_models"
    MODEL_SUBDIRS: List[str] = [
        "checkpoints",
        "unet",
        "loras",
        "vae",
        "controlnet",
        "clip",
        "clip_vision",
        "upscalers",
        "animatediff",
        "ipadapter",
    ]

    def _get_shared_models_dir(self, ctx: AppContext) -> Path:
        """获取共享模型目录路径"""
        return ctx.base_dir / self.SHARED_MODELS_DIR

    def _ensure_model_directories(self, ctx: AppContext) -> None:
        """创建所有模型子目录"""
        shared_models = self._get_shared_models_dir(ctx)
        
        if not shared_models.exists():
            shared_models.mkdir(parents=True, exist_ok=True)
            logger.info(f"  -> 创建模型根目录: {shared_models}")
        
        for subdir_name in self.MODEL_SUBDIRS:
            subdir = shared_models / subdir_name
            if not subdir.exists():
                subdir.mkdir(parents=True, exist_ok=True)
                logger.info(f"  -> 创建子目录: {subdir_name}/")
            os.chmod(subdir, 0o755)

    def _copy_extra_paths_config(self, ctx: AppContext) -> bool:
        """将 extra_model_paths.yaml 模板渲染后写入 ComfyUI 目录"""
        template = self.get_addon_dir(ctx) / self.EXTRA_PATHS_FILENAME
        comfy_dir = ctx.artifacts.comfy_dir
        if not comfy_dir:
            return False
        target = comfy_dir / self.EXTRA_PATHS_FILENAME

        if not template.exists():
            logger.warning(f"  -> [WARN] 模板文件不存在: {template}")
            return False

        shared_models_dir = ctx.base_dir / self.SHARED_MODELS_DIR
        rendered = template.read_text(encoding="utf-8").replace(
            "__BASE_PATH__", str(shared_models_dir)
        )

        if target.exists() and target.read_text(encoding="utf-8") == rendered:
            return False

        target.write_text(rendered, encoding="utf-8")
        return True

    @hookimpl
    def setup(self, context: AppContext) -> None:
        """初始化钩子：创建目录并复制配置"""
        logger.info("\n>>> [Models] 开始初始化模型目录结构...")
        ctx = context

        shared_models = self._get_shared_models_dir(ctx)
        logger.info(f"  -> 共享模型目录: {shared_models}")

        self._ensure_model_directories(ctx)
        logger.info("  -> 模型目录结构初始化完成")

        # 复制 extra_model_paths.yaml 到 ComfyUI 根目录
        comfy_dir = ctx.artifacts.comfy_dir
        if not comfy_dir or not comfy_dir.exists():
            logger.warning(f"  -> [WARN] ComfyUI 目录不存在，跳过 extra_model_paths 配置")
            return

        if self._copy_extra_paths_config(ctx):
            logger.info(f"  -> 已复制 {self.EXTRA_PATHS_FILENAME} 到 ComfyUI 目录")
            ctx.artifacts.extra_model_paths_file = comfy_dir / self.EXTRA_PATHS_FILENAME
        else:
            logger.info(f"  -> [SKIP] {self.EXTRA_PATHS_FILENAME} 已是最新，无需更新")
        
        # 产出
        ctx.artifacts.models_dir = shared_models

    @hookimpl
    def start(self, context: AppContext) -> None:
        pass

    @hookimpl
    def sync(self, context: AppContext) -> None:
        """同步钩子：扫描模型目录生成快照，清理孤儿 .meta"""
        from src.addons.models.lock import generate_snapshot, cleanup_orphan_metas
        from src.addons.models.config import LOCK_FILE

        logger.info("\n>>> [Models] 开始生成模型快照...")

        models_dir = context.artifacts.models_dir
        if not models_dir or not models_dir.exists():
            logger.warning("  -> [WARN] 模型目录不存在，跳过快照生成")
            return

        # 1. 清理孤儿 .meta 文件
        cleaned = cleanup_orphan_metas(models_dir)
        if cleaned > 0:
            logger.info(f"  -> 已清理 {cleaned} 个孤儿 .meta 文件")

        # 2. 加载上一次 lock (用于增量 hash)
        previous_lock = load_yaml(LOCK_FILE)

        # 3. 生成快照
        snapshot = generate_snapshot(models_dir, previous_lock)

        model_count = len(snapshot.get("models", []))
        if model_count == 0:
            logger.info("  -> 模型目录为空，跳过快照写入")
            return

        # 4. 写入 model-lock.yaml
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(LOCK_FILE, snapshot)
        logger.info(f"  -> 快照已保存: {LOCK_FILE} ({model_count} 个模型)")
"""
Models Addon - ComfyUI 模型目录管理

基于 Task Subsystem 的实现：
- Setup: SetupModelsSymlinkTask, MigrateExistingModelsTask
"""
from pathlib import Path

from src.core.interface import BaseAddon, AppContext, hookimpl
from src.core.runtime import require_managed_storage_mount
from src.core.task import TaskRunner
from src.core.utils import logger


class ModelAddon(BaseAddon):
    """ComfyUI 模型目录管理插件
    
    核心职责：
    1. Setup: 将 ComfyUI/models/ 软链接到数据盘 (autodl-tmp/models/)
    """
    
    module_dir = "models"
    MODELS_DIR_NAME = "models"  # ComfyUI 原生目录名
    
    # Setup 阶段先迁移物理目录，再确认软链接。
    SETUP_TASKS = [
        "MigrateExistingModelsTask",
        "SetupModelsSymlinkTask",
    ]
    
    def _get_target_models_dir(self, ctx: AppContext) -> Path:
        """获取数据盘上的模型目录路径"""
        return ctx.models_dir or (ctx.base_dir / self.MODELS_DIR_NAME)

    def _get_comfy_models_dir(self, ctx: AppContext) -> Path:
        """获取 ComfyUI 的 models 目录路径"""
        comfy_dir = ctx.artifacts.comfy_dir
        if not comfy_dir:
            raise RuntimeError("ComfyUI 目录未初始化")
        return comfy_dir / self.MODELS_DIR_NAME

    @hookimpl
    def setup(self, context: AppContext) -> None:
        """初始化钩子：运行 Setup 阶段 Task"""
        logger.info("\n>>> [Models] 开始初始化模型目录...")
        ctx = context

        comfy_dir = ctx.artifacts.comfy_dir
        if not comfy_dir or not comfy_dir.exists():
            logger.warning(f"  -> [WARN] ComfyUI 目录不存在，跳过 models 配置")
            return

        target_models = self._get_target_models_dir(ctx)
        require_managed_storage_mount(target_models)
        logger.info(f"  -> 目标模型目录: {target_models}")

        # 运行 Setup Tasks
        from src.addons.models.tasks import (
            SetupModelsSymlinkTask,
            MigrateExistingModelsTask,
        )
        
        ok = TaskRunner.run_tasks(
            tasks=[
                MigrateExistingModelsTask(),
                SetupModelsSymlinkTask(),
            ],
            ctx=ctx,
            addon_name="Models"
        )
        if not ok:
            raise RuntimeError("Models setup failed; ComfyUI/models is not safely linked")
        
        # 产出
        ctx.artifacts.models_dir = target_models

    @hookimpl
    def start(self, context: AppContext) -> None:
        """启动钩子：无操作"""
        pass

    @hookimpl
    def stop(self, context: AppContext) -> None:
        """Stopping ComfyUI must not scan, migrate, or snapshot model data."""
        return None

"""
Models Addon - ComfyUI 模型目录管理

基于 Task Subsystem 的实现：
- Setup: SetupModelsSymlinkTask, MigrateExistingModelsTask
- Sync: CheckOrphanFilesTask, CleanupOrphanMetasTask, GenerateSnapshotTask
"""
from pathlib import Path

from src.core.interface import BaseAddon, AppContext, hookimpl
from src.core.task import TaskRunner
from src.core.utils import logger


class ModelAddon(BaseAddon):
    """ComfyUI 模型目录管理插件
    
    核心职责：
    1. Setup: 将 ComfyUI/models/ 软链接到数据盘 (autodl-tmp/models/)
    2. Sync: 检查软链接状态，迁移残留文件，生成模型快照
    """
    
    module_dir = "models"
    MODELS_DIR_NAME = "models"  # ComfyUI 原生目录名
    
    # Setup 阶段 Task 列表 (按 priority 顺序)
    SETUP_TASKS = [
        "SetupModelsSymlinkTask",
        "MigrateExistingModelsTask",
    ]
    
    # Sync 阶段 Task 列表 (按 priority 顺序)
    SYNC_TASKS = [
        "CheckOrphanFilesTask",
        "CleanupOrphanMetasTask",
        "GenerateSnapshotTask",
    ]

    def _get_target_models_dir(self, ctx: AppContext) -> Path:
        """获取数据盘上的模型目录路径"""
        return ctx.base_dir / self.MODELS_DIR_NAME

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
        logger.info(f"  -> 目标模型目录: {target_models}")

        # 运行 Setup Tasks
        from src.addons.models.tasks import (
            SetupModelsSymlinkTask,
            MigrateExistingModelsTask,
        )
        
        TaskRunner.run_tasks(
            tasks=[
                SetupModelsSymlinkTask(),
                MigrateExistingModelsTask(),
            ],
            ctx=ctx,
            addon_name="Models"
        )
        
        # 产出
        ctx.artifacts.models_dir = target_models

    @hookimpl
    def start(self, context: AppContext) -> None:
        """启动钩子：无操作"""
        pass

    @hookimpl
    def sync(self, context: AppContext) -> None:
        """同步钩子：运行 Sync 阶段 Task"""
        logger.info("\n>>> [Models] 开始同步模型数据...")

        models_dir = context.artifacts.models_dir
        if not models_dir:
            models_dir = self._get_target_models_dir(context)
        
        if not models_dir.exists():
            logger.warning("  -> [WARN] 模型目录不存在，跳过")
            return

        # 运行 Sync Tasks
        from src.addons.models.tasks import (
            CheckOrphanFilesTask,
            CleanupOrphanMetasTask,
            GenerateSnapshotTask,
        )
        
        TaskRunner.run_tasks(
            tasks=[
                CheckOrphanFilesTask(),
                CleanupOrphanMetasTask(),
                GenerateSnapshotTask(),
            ],
            ctx=context,
            addon_name="Models"
        )

"""Safely migrate files if ComfyUI/models becomes a physical directory."""
from dataclasses import dataclass

from src.addons.models.tasks.migrate_existing_models import MigrateExistingModelsTask
from src.core.interface import AppContext
from src.core.task import BaseTask, TaskResult
from src.core.utils import logger


@dataclass
class CheckOrphanFilesTask(BaseTask):
    """检查并迁移残留文件 Task"""
    
    name: str = "CheckOrphanFiles"
    description: str = "检查并迁移 ComfyUI 物理目录中的残留文件"
    priority: int = 10
    
    def execute(self, ctx: AppContext) -> TaskResult:
        logger.info(f"  -> [Task] {self.name}: 检查残留文件...")
        return MigrateExistingModelsTask().execute(ctx)

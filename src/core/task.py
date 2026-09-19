"""
Task Subsystem - 细粒度任务抽象

提供 Addon 内部的可插拔任务机制，支持：
- 优先级排序执行
- 内部幂等检测
- 配置驱动的启用/禁用

使用方式:
    1. 继承 BaseTask 实现 execute() 方法
    2. 在 Addon 的 get_tasks() 中返回 Task 列表
    3. 在 setup()/start()/stop() 中调用 TaskRunner.run_tasks()
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from src.core.interface import AppContext


class TaskResult(Enum):
    """Task 执行结果"""
    SUCCESS = "success"   # 执行成功（包括修复成功）
    SKIPPED = "skipped"   # 跳过（环境已健康，无需修复）
    FAILED = "failed"     # 执行失败


@dataclass
class BaseTask(ABC):
    """
    Task 基类
    
    子类必须实现:
    - execute(): 执行任务逻辑，内部自行检测是否需要执行
    
    属性:
        name: Task 名称，用于日志输出
        description: Task 描述
        enabled: 是否启用，可通过 manifest.yaml 控制
        priority: 执行优先级，数值小的先执行
    
    Example:
        @dataclass
        class MyTask(BaseTask):
            name: str = "MyTask"
            priority: int = 10
            
            def execute(self, ctx: AppContext) -> TaskResult:
                if self._is_healthy():
                    return TaskResult.SKIPPED
                # ... do something
                return TaskResult.SUCCESS
    """
    name: str
    description: str = ""
    enabled: bool = True
    priority: int = 100  # 小数优先执行
    
    @abstractmethod
    def execute(self, ctx: "AppContext") -> TaskResult:
        """
        执行任务
        
        实现要求:
        1. 内部检测环境状态，决定是否需要执行
        2. 若环境已健康，返回 SKIPPED
        3. 若执行成功，返回 SUCCESS
        4. 若执行失败，返回 FAILED（或抛出异常）
        
        Args:
            ctx: 应用上下文，提供配置、状态、命令执行等能力
            
        Returns:
            TaskResult: 执行结果
        """
        ...


class TaskRunner:
    """Task 执行器"""
    
    @staticmethod
    def run_tasks(
        tasks: List[BaseTask],
        ctx: "AppContext",
        addon_name: str
    ) -> bool:
        """
        按优先级执行 Task 列表
        
        Args:
            tasks: Task 列表
            ctx: 应用上下文
            addon_name: 所属 Addon 名称（用于日志）
            
        Returns:
            bool: 全部成功返回 True，任一失败返回 False
            
        Raises:
            不抛出异常，失败通过返回值表示
        """
        from src.core.utils import logger
        
        # 过滤已禁用的 Task
        enabled_tasks = [t for t in tasks if t.enabled]
        if not enabled_tasks:
            return True
        
        # 按优先级排序
        sorted_tasks = sorted(enabled_tasks, key=lambda t: t.priority)
        
        for task in sorted_tasks:
            try:
                result = task.execute(ctx)
                
                if result == TaskResult.SUCCESS:
                    logger.info(f"  -> [Task] {task.name}: 完成 ✓")
                elif result == TaskResult.SKIPPED:
                    logger.info(f"  -> [Task] {task.name}: 跳过 (环境已就绪)")
                elif result == TaskResult.FAILED:
                    logger.error(f"  -> [Task] {task.name}: 失败 ✗")
                    return False
                    
            except Exception as e:
                logger.error(f"  -> [Task] {task.name}: 异常 - {e}")
                if ctx.debug:
                    import traceback
                    traceback.print_exc()
                return False
        
        return True

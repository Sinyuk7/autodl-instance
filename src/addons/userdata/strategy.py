"""
用户数据同步策略

提供两种数据同步方式:
  - LocalStrategy: 本地模式，从 .example 复制初始化
  - GitRepoStrategy: Git 仓库模式，clone/pull/push
"""
import os
import shutil
import socket
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List

from src.core.interface import AppContext as Context
from src.core.ports import ICommandRunner
from src.core.utils import logger


class SyncStrategy(ABC):
    """数据同步策略基类"""
    
    @abstractmethod
    def prepare(self, data_dir: Path, context: Context) -> bool:
        """准备数据目录（初始化阶段）"""
        pass
    
    @abstractmethod
    def push(self, data_dir: Path, context: Context) -> None:
        """推送数据变更（同步阶段）"""
        pass


class LocalStrategy(SyncStrategy):
    """本地策略：从 .example 复制，无云端同步"""
    
    def __init__(self, example_dir: Path):
        self.example_dir = example_dir
    
    def prepare(self, data_dir: Path, context: Context) -> bool:
        logger.info(f"  -> 模式: 本地存储 (未配置 userdata_repo)")
        if data_dir.exists():
            logger.info(f"  -> 数据目录已存在，跳过初始化")
            return True
        
        if not self.example_dir.exists():
            logger.warning(f"  -> 模板目录不存在，创建空目录")
            data_dir.mkdir(parents=True, exist_ok=True)
            return True
        
        logger.info(f"  -> 从模板初始化本地数据...")
        shutil.copytree(self.example_dir, data_dir)
        return True
    
    def push(self, data_dir: Path, context: Context) -> None:
        logger.info(f"  -> 数据已保存在本地: {data_dir}")
        logger.info(f"  -> 提示: 配置 sync.userdata_repo 可启用云端备份")


class GitRepoStrategy(SyncStrategy):
    """Git 仓库策略：clone/pull 初始化，push 同步"""
    
    def __init__(self, repo_url: str, dir_name: str, cmd: ICommandRunner):
        self.repo_url = repo_url
        self.dir_name = dir_name
        self.cmd = cmd
    
    def _run_git(self, args: List[str], cwd: Path, timeout: int = 120) -> tuple[bool, str]:
        """通过注入的命令执行器执行 Git 命令"""
        try:
            result = self.cmd.run(
                ["git"] + args, cwd=cwd,
                check=False, timeout=timeout,
            )
            return (result.returncode == 0, 
                    result.stdout.strip() if result.returncode == 0 else result.stderr.strip())
        except Exception as e:
            return False, str(e)
    
    def _is_git_repo(self, path: Path) -> bool:
        return (path / ".git").exists()
    
    def _is_rebase_in_progress(self, path: Path) -> bool:
        """检查是否处于 rebase 中间状态"""
        git_dir = path / ".git"
        return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()

    def _get_commit_message(self) -> str:
        """生成格式化的提交信息，包含主机名、用户名和时间戳"""
        hostname = socket.gethostname()
        username = os.getenv("USER") or os.getenv("USERNAME") or "unknown"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"Auto sync from {hostname} by {username} at {timestamp}"

    def _has_local_changes(self, path: Path) -> bool:
        """检查是否有未提交的本地修改"""
        ok, status = self._run_git(["status", "--porcelain"], path)
        return ok and bool(status.strip())

    def prepare(self, data_dir: Path, context: Context) -> bool:
        logger.info(f"  -> 模式: Git 仓库同步")
        
        # 已存在且是 Git 仓库 → pull
        if data_dir.exists() and self._is_git_repo(data_dir):
            # 检查是否有未完成的 rebase，先中止
            if self._is_rebase_in_progress(data_dir):
                logger.warning(f"  -> 检测到未完成的 rebase，正在中止...")
                self._run_git(["rebase", "--abort"], data_dir)
            
            # 检查本地修改，先 stash
            has_changes = self._has_local_changes(data_dir)
            if has_changes:
                logger.info(f"  -> 暂存本地修改...")
                self._run_git(["stash", "push", "-m", "auto-stash before pull"], data_dir)
            
            logger.info(f"  -> 拉取最新数据...")
            ok, msg = self._run_git(["pull", "--rebase"], data_dir)
            
            # 恢复 stash
            if has_changes:
                logger.info(f"  -> 恢复本地修改...")
                pop_ok, pop_msg = self._run_git(["stash", "pop"], data_dir)
                if not pop_ok:
                    logger.warning(f"  -> stash pop 冲突，本地修改保留在 stash 中: {pop_msg}")
            
            if not ok:
                logger.warning(f"  -> Git pull 失败: {msg}，尝试恢复干净状态...")
                # rebase 失败时中止，恢复到干净状态
                if self._is_rebase_in_progress(data_dir):
                    abort_ok, abort_msg = self._run_git(["rebase", "--abort"], data_dir)
                    if abort_ok:
                        logger.info(f"  -> 已中止 rebase，使用本地数据继续")
                    else:
                        logger.warning(f"  -> rebase --abort 失败: {abort_msg}")
                else:
                    logger.info(f"  -> 使用本地数据继续")
            return True
        
        # 存在但非 Git 仓库 → 备份后 clone
        if data_dir.exists():
            backup = data_dir.parent / f"{self.dir_name}.backup_{datetime.now():%Y%m%d_%H%M%S}"
            logger.info(f"  -> 备份现有数据到 {backup.name}")
            shutil.move(str(data_dir), str(backup))
        
        # Clone
        logger.info(f"  -> 克隆私有仓库...")
        ok, msg = self._run_git(["clone", self.repo_url, self.dir_name], data_dir.parent)
        if not ok:
            logger.error(f"  -> Git clone 失败: {msg}")
            return False
        return True
    
    def push(self, data_dir: Path, context: Context) -> None:
        if not self._is_git_repo(data_dir):
            logger.warning(f"  -> 非 Git 仓库，跳过推送")
            return
        
        # 检查变更
        ok, status = self._run_git(["status", "--porcelain"], data_dir)
        if not ok or not status:
            logger.info(f"  -> 无变更需要同步")
            return
        
        # Add + Commit + Push
        self._run_git(["add", "."], data_dir)
        commit_msg = self._get_commit_message()
        ok, msg = self._run_git(["commit", "-m", commit_msg], data_dir)
        if not ok and "nothing to commit" not in msg:
            logger.error(f"  -> Git commit 失败: {msg}")
            return
        
        ok, msg = self._run_git(["push"], data_dir)
        if ok:
            logger.info(f"  -> 已同步到远程仓库")
        else:
            logger.error(f"  -> Git push 失败: {msg}")

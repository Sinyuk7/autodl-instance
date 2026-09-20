"""Manage direct models/output subdirectories; never migrate their root files."""
import fcntl
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from src.lib.migration.transfer import record_path, transfer_directory
from src.core.runtime import require_managed_storage_mount
from src.core.utils import logger


@dataclass(frozen=True)
class MigrationManager:
    comfy_dir: Path
    models_dir: Path
    output_dir: Path
    user_dir: Path
    manage_models: bool = True

    @property
    def links(self) -> tuple[tuple[Path, Path], ...]:
        return tuple((self.comfy_dir / name, target) for name, target in (
            ("models", self.models_dir), ("output", self.output_dir), ("user", self.user_dir)
        ))

    @property
    def state_dir(self) -> Path:
        return self.comfy_dir / ".autodl-layout"

    def validate(self, *, migration: bool = False) -> None:
        require_managed_storage_mount(self.comfy_dir, *(target for _, target in self.links))
        if self.comfy_dir.exists() and not self.comfy_dir.is_dir():
            raise RuntimeError(f"ComfyUI 路径不是目录: {self.comfy_dir}")
        targets = [target.resolve() for _, target in self.links]
        comfy = self.comfy_dir.resolve()
        for target in targets:
            if target == comfy or comfy in target.parents or target in comfy.parents:
                raise RuntimeError(f"数据目标与 ComfyUI 目录重叠: {target}")
        for i, target in enumerate(targets):
            for other in targets[i + 1:]:
                if target == other or target in other.parents or other in target.parents:
                    raise RuntimeError(f"数据目标目录重叠: {target}, {other}")
        for source, target in self.links:
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                raise RuntimeError(f"数据目标必须是实体目录: {target}")
            if source.is_symlink():
                if source.resolve() != target.resolve():
                    raise RuntimeError(f"根目录链接指向其他位置，拒绝自动切换: {source}")
                # Preserve legacy whole-root links; do not traverse/migrate them.
            elif source.exists() and not source.is_dir():
                raise RuntimeError(f"源路径不是目录，保留原文件: {source}")
        if self.state_dir.is_symlink():
            raise RuntimeError(f"状态目录不能是软链接: {self.state_dir}")

    @contextmanager
    def _locked(self):
        self.state_dir.mkdir(mode=0o700, exist_ok=True)
        with (self.state_dir / "lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("另一个 init/migrate 正在处理数据目录") from None
            yield

    def _children(self, source: Path, target: Path):
        # Manage visible direct children only. Hidden contents within a managed
        # directory still count as data and must be preserved.
        names = {p.name for p in source.iterdir()} | {p.name for p in target.iterdir()}
        for name in sorted(names):
            if name.startswith("."):
                continue
            left, right = source / name, target / name
            if (left.is_dir() or right.is_dir() or left.is_symlink() or right.is_symlink()
                    or record_path(self.state_dir, left).exists()):
                yield left, right

    def _initialize_child(self, source: Path, target: Path, *, merge_conflicts: bool = False) -> None:
        if record_path(self.state_dir, source).exists():
            transfer_directory(source, target, self.state_dir)
            return
        if source.is_symlink():
            if not target.is_symlink() and target.is_dir() and source.resolve() == target.resolve():
                return
            logger.warning("跳过错误或失效链接: %s", source)
            return
        if target.is_symlink() or (source.exists() and not source.is_dir()) or (
            target.exists() and not target.is_dir()
        ):
            logger.warning("跳过类型冲突或目标链接: %s -> %s", source, target)
            return
        if not source.exists() or not any(source.iterdir()):
            target.mkdir(exist_ok=True)
            if source.exists():
                source.rmdir()
            source.symlink_to(target)
            logger.info("链接已建立: %s -> %s", source, target)
        elif not target.exists() or not any(target.iterdir()):
            transfer_directory(source, target, self.state_dir)
            logger.info("子目录已迁移并链接: %s -> %s", source, target)
        elif merge_conflicts:
            from src.lib.migration.merge import merge_directory
            conflicts = (target.parent.parent / ".autodl-model-conflicts" / source.name
                         if source.parent.name == "models" else
                         target.parent.parent / ".autodl-migration-conflicts" / "output" / source.name)
            merge_directory(source, target, conflicts)
            self._initialize_child(source, target)
        else:
            logger.warning("双方目录都有内容，保持原状；需要合并时执行 autodl migrate: %s", source)

    def initialize(self) -> None:
        self.run(merge_conflicts=False)

    def migrate(self) -> None:
        self.run(merge_conflicts=True)

    def run(self, *, merge_conflicts: bool = False) -> None:
        self.validate()
        for _, target in self.links:
            target.mkdir(parents=True, exist_ok=True)
        if not self.comfy_dir.is_dir():
            return
        with self._locked():
            for source, target in (self.links[:2] if self.manage_models else self.links[1:2]):
                if source.is_symlink():
                    logger.warning("保留旧版根目录链接，未改为子目录布局: %s", source)
                    continue
                source.mkdir(exist_ok=True)
                for left, right in self._children(source, target):
                    self._initialize_child(left, right, merge_conflicts=merge_conflicts)
            # User data retains its previous whole-directory policy; it must not
            # prevent models/output from being initialized.
            source, target = self.links[2]
            if not source.is_symlink():
                if source.exists() and any(source.iterdir()) and merge_conflicts:
                    from src.lib.migration.merge import merge_directory
                    merge_directory(source, target,
                                    target.parent / ".autodl-migration-conflicts" / target.name)
                if source.exists() and any(source.iterdir()):
                    logger.warning("user 已有数据，保留原状；迁移请执行 autodl migrate: %s", source)
                else:
                    if source.exists():
                        source.rmdir()
                    source.symlink_to(target)

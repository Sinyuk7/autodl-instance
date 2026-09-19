"""Boot-time links and explicit data migration, without installers or networking."""
from dataclasses import dataclass
from pathlib import Path

from src.core.runtime import require_managed_storage_mount


@dataclass(frozen=True)
class DataLayout:
    comfy_dir: Path
    models_dir: Path
    output_dir: Path
    user_dir: Path

    @property
    def links(self) -> tuple[tuple[Path, Path], ...]:
        return tuple((self.comfy_dir / name, target) for name, target in (
            ("models", self.models_dir), ("output", self.output_dir), ("user", self.user_dir)
        ))

    def validate(self, *, migration: bool = False) -> None:
        """Check every link before changing any data path."""
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
            if target.is_symlink() and not target.exists():
                raise RuntimeError(f"目标是失效链接，拒绝写入: {target}")
            if target.exists() and not target.is_dir():
                raise RuntimeError(f"数据目标不是目录: {target}")
            if source.is_symlink():
                if source.resolve() != target.resolve():
                    raise RuntimeError(f"链接指向其他位置，拒绝自动切换: {source} -> {source.readlink()}")
            elif source.exists():
                if not source.is_dir():
                    raise RuntimeError(f"源路径不是目录，保留原文件: {source}")
                if not migration and any(source.iterdir()):
                    raise RuntimeError(f"目录已有数据，保留原状；请先执行 autodl migrate: {source}")

    def initialize(self) -> None:
        self.validate()
        for _, target in self.links:
            target.mkdir(parents=True, exist_ok=True)
        # Before installation, create only storage targets. Do not create a partial
        # ComfyUI checkout that could interfere with comfy-cli installation.
        if not self.comfy_dir.is_dir():
            return
        for source, target in self.links:
            if source.is_symlink():
                continue
            if source.exists():
                source.rmdir()  # Refuses if a writer added files after validation.
            source.symlink_to(target)

    def migrate(self) -> None:
        """Merge physical source directories; init alone owns link creation."""
        from src.addons.workspace.plugin import WorkspaceAddon
        from src.addons.models.tasks.migrate_existing_models import MigrateExistingModelsTask

        self.validate(migration=True)
        for source, target in self.links:
            if source.is_symlink() or not source.exists():
                continue
            if source.name == "models":
                MigrateExistingModelsTask()._migrate_directory_contents(source, target)
            else:
                conflicts = target.parent / ".autodl-migration-conflicts" / target.name
                WorkspaceAddon()._merge_directory(source, target, conflicts)
            # Leave an empty source directory for init. Repeated migrate is safe.

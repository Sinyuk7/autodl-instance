import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.addons.models.plugin import ModelAddon
from src.addons.models.tasks.migrate_existing_models import (
    MigrateExistingModelsTask,
    MigrationStats,
)
from src.addons.models.tasks.setup_models_symlink import SetupModelsSymlinkTask
from src.core.task import TaskResult


def test_migrate_skips_ready_symlink_without_scanning(context_with_comfy, monkeypatch):
    task = MigrateExistingModelsTask()
    target_models = context_with_comfy.base_dir / "models"
    target_models.mkdir(parents=True, exist_ok=True)

    comfy_models = MagicMock(spec=Path)
    comfy_models.is_symlink.return_value = True
    comfy_models.resolve.return_value = target_models.resolve()

    monkeypatch.setattr(task, "_get_comfy_models_dir", lambda ctx: comfy_models)
    monkeypatch.setattr(task, "_get_target_models_dir", lambda ctx: target_models)

    migrate_spy = MagicMock()
    monkeypatch.setattr(task, "_migrate_directory_contents", migrate_spy)

    result = task.execute(context_with_comfy)

    assert result == TaskResult.SKIPPED
    migrate_spy.assert_not_called()


def test_migrate_directory_preserves_all_distinct_conflicts(tmp_path, caplog):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()

    (src / "model.safetensors").write_bytes(b"src-model")
    (dst / "model.safetensors").write_bytes(b"dst-model")
    (src / "README.md").write_text("src readme", encoding="utf-8")
    (dst / "README.md").write_text("dst readme", encoding="utf-8")
    (src / "put_checkpoints_here").write_text("", encoding="utf-8")
    (dst / "put_checkpoints_here").write_text("", encoding="utf-8")
    (src / ".cache.meta").write_text("meta", encoding="utf-8")
    (dst / ".cache.meta").write_text("meta", encoding="utf-8")

    task = MigrateExistingModelsTask()

    with caplog.at_level(logging.INFO, logger="autodl_setup"):
        stats = task._migrate_directory_contents(src, dst)

    assert stats == MigrationStats(migrated=0, model_conflicts=1, auxiliary_conflicts=3)
    conflicts = tmp_path / ".autodl-model-conflicts"
    assert (conflicts / "model.safetensors").read_bytes() == b"src-model"
    assert (conflicts / "README.md").read_text(encoding="utf-8") == "src readme"
    assert not (conflicts / "put_checkpoints_here").exists()
    assert not (conflicts / ".cache.meta").exists()


def test_migrate_preserves_conflict_and_builds_symlink(context_with_comfy, caplog):
    task = MigrateExistingModelsTask()
    comfy_models = context_with_comfy.artifacts.comfy_dir / "models"
    target_models = context_with_comfy.base_dir / "models"
    target_models.mkdir(parents=True, exist_ok=True)

    (comfy_models / "model.safetensors").write_bytes(b"src-model")
    (target_models / "model.safetensors").write_bytes(b"dst-model")

    with caplog.at_level(logging.INFO, logger="autodl_setup"):
        result = task.execute(context_with_comfy)

    assert result == TaskResult.SUCCESS
    assert comfy_models.is_symlink()
    assert comfy_models.resolve() == target_models.resolve()
    assert (target_models.parent / ".autodl-model-conflicts" / "model.safetensors").read_bytes() == b"src-model"
    assert (target_models / "model.safetensors").read_bytes() == b"dst-model"


def test_migrate_empty_directory_tree_builds_symlink(context_with_comfy):
    task = MigrateExistingModelsTask()
    comfy_models = context_with_comfy.artifacts.comfy_dir / "models"
    target_models = context_with_comfy.base_dir / "models"
    (comfy_models / "checkpoints" / "nested").mkdir(parents=True)

    result = task.execute(context_with_comfy)

    assert result == TaskResult.SUCCESS
    assert comfy_models.is_symlink()
    assert comfy_models.resolve() == target_models.resolve()


def test_setup_symlink_fails_when_physical_directory_still_has_data(context_with_comfy):
    comfy_models = context_with_comfy.artifacts.comfy_dir / "models"
    (comfy_models / "unmigrated.safetensors").write_bytes(b"model")

    result = SetupModelsSymlinkTask().execute(context_with_comfy)

    assert result == TaskResult.FAILED
    assert comfy_models.is_dir()
    assert not comfy_models.is_symlink()


def test_models_addon_propagates_task_failure(context_with_comfy):
    with patch("src.addons.models.plugin.TaskRunner.run_tasks", return_value=False):
        with pytest.raises(RuntimeError, match="Models setup failed"):
            ModelAddon().setup(context_with_comfy)

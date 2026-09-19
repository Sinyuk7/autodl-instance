from src.core.data_layout import DataLayout


def layout(ctx):
    return DataLayout(ctx.artifacts.comfy_dir, ctx.models_dir, ctx.output_dir,
                      ctx.workspace_data_dir / "user")


def test_workspace_keeps_persistent_file_and_preserves_conflict(context_with_comfy):
    source = context_with_comfy.artifacts.comfy_dir / "user"
    target = context_with_comfy.workspace_data_dir / "user"
    target.mkdir(parents=True)
    (source / "settings.json").write_text("new-system-copy", encoding="utf-8")
    (target / "settings.json").write_text("persistent-copy", encoding="utf-8")

    layout(context_with_comfy).migrate()
    layout(context_with_comfy).initialize()

    assert source.is_symlink()
    assert source.resolve() == target.resolve()
    assert (target / "settings.json").read_text(encoding="utf-8") == "persistent-copy"
    conflict = context_with_comfy.workspace_data_dir / ".autodl-migration-conflicts" / "user" / "settings.json"
    assert conflict.read_text(encoding="utf-8") == "new-system-copy"


def test_workspace_merges_new_files_and_is_idempotent(context_with_comfy):
    source = context_with_comfy.artifacts.comfy_dir / "user"
    target = context_with_comfy.workspace_data_dir / "user"
    (source / "default").mkdir()
    (source / "default" / "workflow.json").write_text("{}", encoding="utf-8")

    addon = layout(context_with_comfy)
    addon.migrate()
    addon.initialize()
    addon.initialize()

    assert source.is_symlink()
    assert (target / "default" / "workflow.json").read_text(encoding="utf-8") == "{}"

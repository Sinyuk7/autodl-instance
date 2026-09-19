"""Exercise the real addon chain with mocked installers and temporary storage."""
from src.main import execute


def test_full_setup_preserves_files_and_links_storage(context_with_home):
    ctx = context_with_home
    (ctx.comfy_dir / "models").mkdir()
    (ctx.comfy_dir / "models" / "example.bin").write_bytes(b"model")
    (ctx.comfy_dir / "user").mkdir()
    (ctx.comfy_dir / "user" / "workflow.json").write_text("{}")
    execute("setup", ctx)
    assert ctx.artifacts.comfy_dir == ctx.comfy_dir
    assert (ctx.comfy_dir / "models").resolve() == ctx.models_dir
    assert (ctx.models_dir / "example.bin").read_bytes() == b"model"
    assert (ctx.comfy_dir / "user" / "workflow.json").read_text() == "{}"
    assert (ctx.comfy_dir / "output").resolve() == ctx.output_dir
    assert (ctx.workspace_dir / ".artifacts.json").exists()
    commands = ctx.cmd.all_commands
    assert any(str(ctx.python_env_dir / "bin/comfy") in c for c in commands)
    assert not any("--system" in c for c in commands)

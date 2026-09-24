"""Exercise the real addon chain with mocked installers and temporary storage."""
from src.main import execute


def test_full_setup_installs_without_migrating_or_linking_storage(context_with_home, monkeypatch):
    monkeypatch.setattr("src.lib.network.setup_network", lambda **kwargs: None)
    ctx = context_with_home
    (ctx.comfy_dir / "models").mkdir()
    (ctx.comfy_dir / "models" / "example.bin").write_bytes(b"model")
    (ctx.comfy_dir / "user").mkdir()
    (ctx.comfy_dir / "user" / "workflow.json").write_text("{}")
    execute("setup", ctx)
    assert ctx.artifacts.comfy_dir == ctx.comfy_dir
    assert not (ctx.comfy_dir / "models").is_symlink()
    assert (ctx.comfy_dir / "models" / "example.bin").read_bytes() == b"model"
    assert (ctx.comfy_dir / "user" / "workflow.json").read_text() == "{}"
    assert not (ctx.comfy_dir / "output").is_symlink()
    assert (ctx.workspace_dir / ".artifacts.json").exists()
    commands = ctx.cmd.all_commands
    assert any(str(ctx.python_env_dir / "bin/comfy") in c for c in commands)
    assert not any("--system" in c for c in commands)

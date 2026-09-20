"""Copy-only presets preserve all existing user files."""
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
import yaml
from src.addons.models.preset.copy import ModelCopier, load_preset
from src.addons.models.preset.environment import Settings, configure, configuration_ready, priority_ready, blocks
from src.cli import main


def preset(*paths):
    return {"version": 1, "name": "demo", "models": list(paths)}


@pytest.fixture
def copier(tmp_path):
    source = tmp_path / "fs/models"
    source.mkdir(parents=True)
    return ModelCopier(source, tmp_path / "tmp/models", progress=lambda _: None)


def put(root, rel, content=b"model"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def test_copy_skip_and_no_deletion(copier):
    put(copier.source, "vae/a.pt")
    b = put(copier.local, "vae/b.pt", b"local only")
    c = put(copier.local, "vae/c.pt", b"unrelated")
    result = copier.copy(preset("vae/a.pt", "vae/b.pt"))
    assert result["copied"] == ["vae/a.pt"]
    assert result["skipped"] == ["vae/b.pt"]
    put(copier.source, "vae/a.pt", b"new version")
    assert copier.copy(preset("vae/a.pt"))["skipped"] == ["vae/a.pt"]
    assert (copier.local / "vae/a.pt").read_bytes() == b"model"
    assert b.read_bytes() == b"local only" and c.read_bytes() == b"unrelated"


def test_missing_and_space_are_reported_without_mutation(copier, monkeypatch):
    assert copier.plan(preset("vae/missing.pt"))["missing"] == ["vae/missing.pt"]
    put(copier.source, "vae/a.pt")
    monkeypatch.setattr("src.addons.models.preset.copy.shutil.disk_usage", lambda _: Mock(free=0))
    with pytest.raises(RuntimeError, match="INSUFFICIENT_SPACE"):
        copier.copy(preset("vae/a.pt"))
    assert not copier.local.exists()


def test_interrupted_copy_never_publishes_model(copier, monkeypatch):
    put(copier.source, "vae/a.pt")
    def fail(src, dst, *_):
        dst.write(b"partial")
        raise OSError("disk full")
    monkeypatch.setattr("src.addons.models.preset.copy.shutil.copyfileobj", fail)
    with pytest.raises(OSError):copier.copy(preset("vae/a.pt"))
    assert not list((copier.local / "vae").iterdir())


def test_changed_source_is_not_published(copier, monkeypatch):
    src = put(copier.source, "vae/a.pt")
    def change(source, target, *_):
        target.write(source.read())
        src.write_bytes(b"changed")
    monkeypatch.setattr("src.addons.models.preset.copy.shutil.copyfileobj", change)
    with pytest.raises(RuntimeError, match="Source changed"):
        copier.copy(preset("vae/a.pt"))
    assert not (copier.local / "vae/a.pt").exists()


def test_concurrent_destination_never_overwritten(copier, monkeypatch):
    put(copier.source, "vae/a.pt")
    import os
    link = os.link
    def competing(src, dst):
        dst.write_bytes(b"winner")
        link(src, dst)
    monkeypatch.setattr("src.addons.models.preset.copy.os.link", competing)
    assert copier.copy(preset("vae/a.pt"))["skipped"] == ["vae/a.pt"]
    assert (copier.local / "vae/a.pt").read_bytes() == b"winner"


def test_symlink_escape_rejected(copier, tmp_path):
    outside = put(tmp_path, "outside/a.pt")
    (copier.source / "vae").symlink_to(outside.parent)
    with pytest.raises(ValueError, match="escapes"):
        copier.plan(preset("vae/a.pt"))
    (copier.source / "vae").unlink()
    put(copier.source, "vae/a.pt")
    copier.local.mkdir(parents=True)
    (copier.local / "vae").symlink_to(outside.parent)
    with pytest.raises(ValueError, match="Symlink"):
        copier.copy(preset("vae/a.pt"))


@pytest.mark.parametrize("rel", ["/vae/a.pt", "vae/../a.pt", "vae/.hidden.pt", "vae//a.pt", "unknown/a.pt"])
def test_preset_rejects_invalid_paths(tmp_path, rel):
    (tmp_path / "demo.yaml").write_text(yaml.safe_dump(preset(rel)))
    with pytest.raises(ValueError):load_preset(tmp_path, "demo")


def test_duplicate_category_alias_rejected(tmp_path):
    (tmp_path / "demo.yaml").write_text(yaml.safe_dump(preset("unet/a.pt", "diffusion_models/a.pt")))
    with pytest.raises(ValueError, match="Duplicate"):load_preset(tmp_path, "demo")


def test_cli_dry_run_never_changes_files(settings, monkeypatch, capsys):
    settings.presets.mkdir()
    (settings.presets / "demo.yaml").write_text(yaml.safe_dump(preset("vae/a.pt")))
    put(settings.source, "vae/a.pt")
    monkeypatch.setattr("src.addons.models.preset.cli.Settings.load", lambda _: settings)
    monkeypatch.setattr("src.addons.models.preset.cli.check_storage", lambda _: None)
    for command in (["list"], ["show", "demo"], ["copy", "demo", "--dry-run"]):
        main(["models", "preset", *command])
        assert "demo" in capsys.readouterr().out
    assert not settings.root.exists()
    for cmd in ("reset",):
        with pytest.raises(SystemExit):main(["models", "preset", cmd])


def test_known_legacy_config_upgrade_preserves_user_text(settings):
    path = settings.comfy / "extra_model_paths.yaml"
    prefix = "# user comment\ncustom:\n  base_path: /custom\n  vae: vae\n\n"
    path.write_text(prefix + "# AutoDL local model cache (managed)\n" + yaml.safe_dump({
        "autodl_canonical_models": {"base_path": str(settings.source)},
        "autodl_local_model_cache": {"base_path": str(settings.root / "cache")}}, sort_keys=False))
    configure(settings)
    assert path.read_text().startswith(prefix.rstrip())
    assert "autodl_local_model_cache" not in path.read_text()
    assert configuration_ready(settings)
    assert not configure(settings)["changed"]


def test_download_partial_and_publish(tmp_path, monkeypatch):
    from src.addons.models import downloader
    target = tmp_path / "model.safetensors"
    def incomplete(url, dest):
        assert dest.name.endswith('.part')
        dest.write_bytes(b"partial")
        return False
    monkeypatch.setattr(downloader, "core_download", incomplete)
    assert not downloader.download_to_models("url", target)
    assert not target.exists()
    def complete(url, dest):
        assert dest.read_bytes() == b"partial"
        dest.write_bytes(b"complete")
        return True
    monkeypatch.setattr(downloader, "core_download", complete)
    assert downloader.download_to_models("url", target)
    assert target.read_bytes() == b"complete"
    assert not Path(str(target) + '.part').exists()
    monkeypatch.setattr(downloader, "core_download", Mock(side_effect=AssertionError))
    assert downloader.download_to_models("url", target)


@pytest.fixture
def settings(tmp_path):
    comfy = tmp_path / "ComfyUI"
    comfy.mkdir()
    (comfy / "main.py").touch()
    (comfy / "folder_paths.py").touch()
    return Settings(tmp_path / "fs/models", tmp_path / "tmp/hot", tmp_path / "presets", comfy)


def simulated_paths(settings):
    paths = {}
    for block in blocks(settings).values():
        for category, values in block.items():
            if category in ("base_path", "is_default"):
                continue
            for value in values.splitlines():
                actual = str(Path(block["base_path"]) / value)
                paths.setdefault(category, [])
                if block.get("is_default"):
                    paths[category].insert(0, actual)
                else:
                    paths[category].append(actual)
    return paths


def test_configure_preserves_user_yaml_and_does_not_touch_links(settings):
    yaml_path = settings.comfy / "extra_model_paths.yaml"
    original = "# User comment\nuser_models:\n  base_path: /somewhere\n  vae: vae\n"
    yaml_path.write_text(original)
    assert configure(settings)["changed"]
    assert yaml_path.read_text().startswith(original)
    assert configuration_ready(settings)
    assert not configure(settings)["changed"]
    assert not settings.root.exists()
    assert priority_ready(settings, simulated_paths(settings))
    paths = simulated_paths(settings)
    paths["vae"].reverse()
    assert not priority_ready(settings, paths)


def test_probe_bypasses_proxy_and_does_not_expose_queue(settings, monkeypatch):
    from src.addons.models.preset.environment import probe
    session = Mock()
    queue = Mock()
    queue.json.return_value = {"queue_running": [["sensitive workflow"]], "queue_pending": []}
    paths = Mock()
    paths.json.return_value = simulated_paths(settings)
    session.get.side_effect = [queue, paths]
    context = Mock()
    context.__enter__ = Mock(return_value=session)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("src.addons.models.preset.environment.requests.Session", lambda: context)
    result = probe(settings)
    assert result["state"] == "BUSY"
    assert session.trust_env is False
    assert "sensitive" not in str(result)
    assert all(call.kwargs["allow_redirects"] is False for call in session.get.call_args_list)


def test_mount_check_rejects_system_disk_before_commands(settings):
    from src.addons.models.preset.environment import check_storage
    runner = Mock()
    with pytest.raises(RuntimeError, match="Expected storage"):
        check_storage(settings, runner)
    runner.run.assert_not_called()


@pytest.mark.parametrize("mounted", [True, False])
def test_storage_alias_requires_real_mount(tmp_path, monkeypatch, mounted):
    from src.addons.models.preset.environment import _check_storage_mount
    real = tmp_path / "mounted-storage"
    real.mkdir()
    alias = tmp_path / "autodl-fs"
    alias.symlink_to(real, target_is_directory=True)
    runner = Mock()
    runner.run.return_value.returncode = 0
    monkeypatch.setattr(Path, "is_mount", lambda p: mounted and p == real)
    if mounted:
        _check_storage_mount(alias, alias / "models", runner)
    else:
        with pytest.raises(RuntimeError, match="not mounted"):
            _check_storage_mount(alias, alias / "models", runner)
    assert all(str(real) in call.args[0] for call in runner.run.call_args_list)


def test_storage_alias_rejects_escaped_target(tmp_path):
    from src.addons.models.preset.environment import _check_storage_mount
    real = tmp_path / "mounted-storage"
    real.mkdir()
    alias = tmp_path / "autodl-fs"
    alias.symlink_to(real, target_is_directory=True)
    (real / "models").symlink_to(tmp_path, target_is_directory=True)
    runner = Mock()
    with pytest.raises(RuntimeError, match="Expected storage"):
        _check_storage_mount(alias, alias / "models", runner)
    runner.run.assert_not_called()



def test_model_list_includes_both_roots_but_not_partials(tmp_path, monkeypatch):
    from src.addons.models import downloader
    local, shared = tmp_path / 'local', tmp_path / 'shared'
    put(local, 'vae/local.safetensors')
    put(shared, 'vae/shared.safetensors')
    put(local, 'vae/incomplete.safetensors.part')
    put(local, 'vae/legacy.safetensors')
    put(local, 'vae/legacy.safetensors.aria2')
    monkeypatch.setattr(downloader, 'get_local_models_base', lambda: local)
    monkeypatch.setattr(downloader, 'get_models_base', lambda: shared)
    table = Mock()
    monkeypatch.setattr(downloader.ui, 'print_table', table)
    downloader.cmd_list()
    rows = table.call_args.kwargs['rows']
    assert [(r[0], r[1]) for r in rows] == [('tmp', 'vae/local.safetensors'), ('fs', 'vae/shared.safetensors')]


def test_upgrade_previous_default_fs_configuration(settings):
    expected = blocks(settings)
    old = {
        "autodl_canonical_models": {**expected["autodl_local_models"],
                                    "base_path": str(settings.source)},
        "autodl_local_models": expected["autodl_local_models"],
    }
    path = settings.comfy / "extra_model_paths.yaml"
    prefix = "# keep custom paths\ncustom:\n  base_path: /custom\n  vae: vae\n"
    path.write_text(prefix + "\n# AutoDL model paths (managed)\n" + yaml.safe_dump(old, sort_keys=False))
    assert configure(settings)["changed"]
    assert path.read_text().startswith(prefix)
    assert configuration_ready(settings)
    assert "is_default" not in yaml.safe_load(path.read_text())["autodl_canonical_models"]
    assert not configure(settings)["changed"]


def test_modified_managed_config_is_not_overwritten(settings):
    old = blocks(settings)
    old["autodl_canonical_models"]["base_path"] = "/custom-changed"
    path = settings.comfy / "extra_model_paths.yaml"
    original = "# AutoDL model paths (managed)\n" + yaml.safe_dump(old, sort_keys=False)
    path.write_text(original)
    with pytest.raises(RuntimeError, match="review configuration manually"):
        configure(settings)
    assert path.read_text() == original

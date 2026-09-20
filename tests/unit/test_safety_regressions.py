from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

import pytest

from src.cli import main
from src.core.python_env import ensure_python_env, resolve_target_python, validate_env_path
from src.lib.download.paths import safe_target
from src.lib.utils import save_yaml, load_yaml


@pytest.mark.parametrize('path', ['/tmp/out.bin', '../out.bin', 'loras/../../out.bin'])
def test_download_cannot_escape(tmp_path, path):
    with pytest.raises(ValueError):
        safe_target(tmp_path, path)


def test_download_rejects_symlink_and_meta(tmp_path):
    root = tmp_path / 'downloads'
    root.mkdir()
    (root / 'outside').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        safe_target(root, 'outside/model.bin')
    (root / '.model.bin.meta').symlink_to(tmp_path / 'secret')
    with pytest.raises(ValueError):
        safe_target(root, 'model.bin')


def test_env_never_uses_conda(monkeypatch, tmp_path):
    monkeypatch.setenv('CONDA_PREFIX', '/root/miniconda3')
    assert resolve_target_python(tmp_path) == str(tmp_path / 'bin/python')
    with pytest.raises(ValueError):
        validate_env_path(Path('/root/autodl-tmp/venv'))


def test_env_refuses_nonvenv_directory(app_context):
    (app_context.python_env_dir / 'pyvenv.cfg').unlink()
    with pytest.raises(RuntimeError, match='non-venv'):
        ensure_python_env(app_context)
    assert not app_context.cmd.all_commands


def test_init_preserves_existing_config(tmp_path):
    config = tmp_path / 'config.yaml'
    data = {key: str(tmp_path / key) for key in (
        'base_dir', 'workspace_dir', 'workspace_data_dir', 'models_dir',
        'output_dir', 'downloads_dir', 'cache_dir', 'temp_dir', 'comfy_dir', 'python_env_dir')}
    data['custom'] = 'kept'
    save_yaml(config, data)
    with patch('src.lib.network.setup_network') as network:
        main(['init', '--config-file', str(config)])
    assert load_yaml(config) == data
    network.assert_called_once_with(config_file=config)


@pytest.mark.parametrize('args', [['--help'], ['download', '--help'], ['types'], ['list'], ['status'], ['cache', 'list']])
def test_model_readonly_never_initializes_network(args, monkeypatch):
    from src.addons.models import downloader
    monkeypatch.setattr(sys, 'argv', ['model', *args])
    with patch.object(downloader, 'setup_network') as network, \
         patch.object(downloader, 'cmd_types'), patch.object(downloader, 'cmd_list'), \
         patch.object(downloader, 'cmd_status'), patch.object(downloader, 'cmd_cache_list'):
        try:
            downloader.main()
        except SystemExit as error:
            assert error.code == 0
        network.assert_not_called()


def test_healthy_proxy_reused_without_install_or_restart(tmp_path):
    from src.lib.network.manager import NetworkManager
    from src.lib.network.proxy.base import ProxyConfig
    backend = MagicMock()
    backend.is_running.return_value = True
    backend.health_check.return_value = True
    with patch('src.lib.network.manager._build_proxy_config', return_value=ProxyConfig('')), \
         patch('src.lib.network.manager.MihomoBackend', return_value=backend), \
         patch('src.lib.network.manager.cache_network_decision'):
        NetworkManager()._setup_proxy(False)
    backend.install.assert_not_called()
    backend.update_subscription.assert_not_called()
    backend.start.assert_not_called()


def test_preset_resumes_partial_and_reports_failure(tmp_path, monkeypatch):
    from src.addons.models import downloader
    from src.addons.models.schema import PresetsFile
    from types import SimpleNamespace
    target = tmp_path / 'models' / 'model.bin.part'
    target.parent.mkdir()
    target.write_bytes(b'partial')
    Path(str(target) + '.aria2').touch()
    preset = PresetsFile.model_validate({'presets': {'test': {'models': [
        {'model': 'test', 'url': 'https://example.com/model.bin', 'paths': [{'path': 'model.bin'}]}
    ]}}})
    monkeypatch.setattr(downloader, 'load_presets', lambda: preset)
    monkeypatch.setattr(downloader, 'get_local_models_base', lambda: target.parent)
    monkeypatch.setattr(downloader, 'get_models_base', lambda: tmp_path / 'models')
    monkeypatch.setattr(downloader, 'prepare_download_preflight', lambda *a: SimpleNamespace(ok=True))
    monkeypatch.setattr(downloader, '_report_preflight', lambda *a: True)
    with patch.object(downloader, 'core_download', return_value=False) as download:
        with pytest.raises(SystemExit) as error:
            downloader.cmd_download_preset('test')
    assert error.value.code == 1
    assert download.call_args.args[1] == target
    assert target.read_bytes() == b'partial'


def test_dry_run_never_installs_tools(tmp_path):
    from src.lib.download.manager import DownloadManager
    manager = DownloadManager()
    with patch.object(manager, '_ensure_tools') as install, \
         patch.object(manager.get_strategy('https://example.com'), 'is_available', return_value=False):
        assert not manager.download('https://example.com', tmp_path / 'file.bin', dry_run=True)
    install.assert_not_called()


def test_config_preserves_portable_storage_symlink(tmp_path):
    storage = tmp_path / 'platform-internal'
    storage.mkdir()
    alias = tmp_path / 'autodl-fs'
    alias.symlink_to(storage)
    config = tmp_path / 'config.yaml'
    main(['config', '--config-file', str(config), 'set', 'output-dir', str(alias / 'output')])
    assert load_yaml(config)['output_dir'] == str(alias / 'output')

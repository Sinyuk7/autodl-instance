from pathlib import Path
from unittest.mock import MagicMock, patch

from src.lib.network.manager import _build_proxy_config
from src.lib.network.proxy.base import ProxyConfig
from src.lib.network.proxy.mihomo import MihomoBackend


def test_proxy_config_uses_absolute_workspace_directory(tmp_path: Path):
    workspace = tmp_path / "comfyui-workspace" / "mihomo"
    workspace.mkdir(parents=True)
    (workspace / "config.yaml").write_text("proxies:\n  - name: test\n" * 8, encoding="utf-8")

    with patch("src.lib.network.manager._get_local_secrets", return_value={}), \
         patch("src.lib.network.manager._get_workspace_mihomo_dir", return_value=workspace):
        config = _build_proxy_config(tmp_path / "runtime.yaml")

    assert config is not None
    assert config.config_dir == workspace.resolve()


def test_mihomo_config_test_uses_absolute_paths(tmp_path: Path):
    install_dir = tmp_path / "bin"
    config_dir = tmp_path / "workspace" / "mihomo"
    install_dir.mkdir()
    config_dir.mkdir(parents=True)
    binary = install_dir / "mihomo"
    binary.write_text("binary", encoding="utf-8")
    config_file = config_dir / "config.yaml"
    config_file.write_text("mixed-port: 7890\n", encoding="utf-8")
    backend = MihomoBackend(ProxyConfig("", install_dir=install_dir, config_dir=config_dir))

    completed = MagicMock(returncode=0)
    with patch("src.lib.network.proxy.mihomo.subprocess.run", return_value=completed) as run:
        assert backend._validate_config()

    command = run.call_args.args[0]
    assert command == [
        str(binary.resolve()),
        "-t",
        "-d", str(config_dir.resolve()),
        "-f", str(config_file.resolve()),
    ]


def test_mihomo_refuses_to_stop_unowned_pid(tmp_path: Path):
    install_dir = tmp_path / "bin"
    config_dir = tmp_path / "mihomo"
    install_dir.mkdir()
    config_dir.mkdir()
    (install_dir / "mihomo").write_text("binary", encoding="utf-8")
    (config_dir / "mihomo.pid").write_text("1234", encoding="utf-8")
    backend = MihomoBackend(ProxyConfig("", install_dir=install_dir, config_dir=config_dir))

    with patch("src.lib.network.proxy.mihomo.os.kill") as kill, \
         patch.object(backend, "_process_matches", return_value=False):
        assert not backend.stop()

    kill.assert_called_once_with(1234, 0)

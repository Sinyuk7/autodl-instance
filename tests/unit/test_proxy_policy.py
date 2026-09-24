import os
import socket
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.lib.network import policy
from src.lib.network.commands import dispatch, install_git
from src.lib.network.manager import NetworkManager
from src.lib.network.proxy.base import ProxyConfig


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for key in policy.PROXY_KEYS:
        monkeypatch.delenv(key, raising=False)
    # Undo even direct os.environ writes performed by the manager.
    with patch.dict(os.environ, dict(os.environ), clear=True):
        yield


def test_off_clears_inherited_proxies_without_start_or_fallback(tmp_path):
    config = tmp_path / "config.yaml"
    policy.write_mode("off", config)
    os.environ.update({key: "http://stale:1234" for key in policy.PROXY_KEYS})
    with patch("src.lib.network.manager._build_proxy_config") as build, \
         patch("src.lib.network.manager.load_autodl_turbo") as turbo:
        NetworkManager(config)._setup_proxy(False)
    build.assert_not_called()
    turbo.assert_not_called()
    assert not any(key in os.environ for key in policy.PROXY_KEYS)
    assert policy.shell_environment(config).startswith("unset ")


def test_on_requires_mihomo_and_does_not_persist_failure(tmp_path):
    config = tmp_path / "config.yaml"
    policy.write_mode("off", config)
    with patch("src.lib.network.manager._build_proxy_config", return_value=None), \
         patch("src.lib.network.manager.load_autodl_turbo") as turbo:
        with pytest.raises(RuntimeError, match="拒绝静默回退"):
            dispatch(SimpleNamespace(config_file=config, proxy_command="on"))
    assert policy.read_mode(config) == "off"
    turbo.assert_not_called()


def test_reused_manager_obeys_changed_switch(tmp_path):
    config = tmp_path / "config.yaml"
    backend = MagicMock()
    backend.is_running.return_value = backend.health_check.return_value = True
    manager = NetworkManager(config)
    with patch("src.lib.network.manager._build_proxy_config", return_value=ProxyConfig("")), \
         patch("src.lib.network.manager.MihomoBackend", return_value=backend), \
         patch("src.lib.network.manager.load_hf_mirror"), \
         patch("src.lib.network.manager.load_api_tokens"), \
         patch("src.lib.network.manager.cache_network_decision"):
        policy.write_mode("on", config)
        manager.setup(False)
        assert os.environ["https_proxy"] == "http://127.0.0.1:7890"
        policy.write_mode("off", config)
        manager.setup(False)
        assert "https_proxy" not in os.environ
    backend.start.assert_not_called()


def test_shell_exports_are_readonly_and_contain_no_tokens(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    policy.write_mode("on", config)
    monkeypatch.setenv("HF_TOKEN", "not-for-shell-output")
    script = policy.shell_environment(config)
    assert "not-for-shell-output" not in script
    result = subprocess.run(["bash", "-c", script + '\nprintf "%s" "$https_proxy"'], capture_output=True, text=True, check=True)
    assert result.stdout == "http://127.0.0.1:7890"
    policy.write_mode("off", config)
    result = subprocess.run(["bash", "-c", script + "\n" + policy.shell_environment(config) + '\n[[ -z ${https_proxy+x} && -z ${ALL_PROXY+x} ]]'])
    assert result.returncode == 0


def test_git_integration_switches_https_and_ssh_without_changing_other_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    config = tmp_path / "config.yaml"
    (tmp_path / ".gitconfig").write_text('[user]\n name = Test\n')
    policy.write_mode("on", config)
    install_git(config)
    install_git(config)
    def value(key):
        return subprocess.check_output(["git", "config", "--global", "--includes", "--get-all", key], text=True).strip()
    assert value("http.proxy") == "http://127.0.0.1:7890"
    assert "ssh_connect" in value("core.sshCommand")
    assert len(value("include.path").splitlines()) == 1
    policy.write_mode("off", config)
    assert value("http.proxy") == ""
    assert value("core.sshCommand") == "ssh"
    assert value("user.name") == "Test"


def test_git_install_refuses_custom_ssh_launcher(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    (tmp_path / ".gitconfig").write_text('[core]\n sshCommand = custom-ssh\n')
    policy.write_mode("on", tmp_path / "config.yaml")
    with pytest.raises(RuntimeError, match="未覆盖"):
        install_git(tmp_path / "config.yaml")


@pytest.mark.parametrize("action", ["setup", "start", "stop"])
def test_lifecycle_network_before_children_only_for_start_setup(action, app_context):
    from src.main import execute
    events = []
    addon = MagicMock()
    getattr(addon, action).side_effect = lambda ctx: events.append("child")
    with patch("src.lib.network.setup_network", side_effect=lambda **kwargs: events.append("network")), \
         patch("src.main.create_pipeline", return_value=[addon]):
        execute(action, app_context)
    assert events == (["child"] if action == "stop" else ["network", "child"])


def test_download_initializes_network_before_tools_and_transfer(tmp_path):
    from src.lib.download.manager import DownloadManager
    manager = DownloadManager()
    events = []
    strategy = MagicMock()
    strategy.download.side_effect = lambda *args, **kwargs: events.append("download") or True
    with patch("src.lib.network.setup_network", side_effect=lambda: events.append("network")), \
         patch.object(manager, "_ensure_tools", side_effect=lambda: events.append("tools")), \
         patch.object(manager, "get_strategy", return_value=strategy):
        assert manager.download("https://example.org/test", tmp_path / "file")
    assert events == ["network", "tools", "download"]


def test_ssh_connect_keeps_banner_and_uses_github_443(tmp_path, monkeypatch):
    from src.lib.network import ssh_connect
    policy.write_mode("on", tmp_path / "config.yaml")
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    monkeypatch.setattr(ssh_connect, "proxy_port", lambda: server.getsockname()[1])
    requests = []
    def accept():
        with server.accept()[0] as conn:
            data = b""
            while not data.endswith(b"\r\n\r\n"):
                data += conn.recv(1)
            requests.append(data)
            conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\nSSH-2.0-test\r\n")
    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    try:
        with ssh_connect.connect("github.com", 22, tmp_path / "config.yaml") as conn:
            assert conn.recv(128) == b"SSH-2.0-test\r\n"
        thread.join(timeout=3)
        assert requests[0].startswith(b"CONNECT ssh.github.com:443 HTTP/1.1")
    finally:
        server.close()


def test_corrupt_policy_does_not_silently_enable_proxy(tmp_path):
    (tmp_path / "proxy-state.json").write_text('{"mode":"invalid"}')
    with pytest.raises(ValueError):
        policy.shell_environment(tmp_path / "config.yaml")


def test_saved_profile_starts_without_subscription_server(tmp_path):
    profile = tmp_path / "mihomo" / "config.yaml"
    profile.parent.mkdir()
    profile.write_text("# saved profile\n" * 20)
    backend = MagicMock()
    backend.is_running.return_value = False
    backend.install.return_value = backend.start.return_value = backend.health_check.return_value = True
    config = ProxyConfig("", config_dir=profile.parent)
    with patch("src.lib.network.manager._build_proxy_config", return_value=config), \
         patch("src.lib.network.manager.MihomoBackend", return_value=backend), \
         patch("src.lib.network.manager.load_autodl_turbo"), \
         patch("src.lib.network.manager.cache_network_decision"), \
         patch("src.lib.network.proxy.config.patch_config") as repair:
        NetworkManager(tmp_path / "config.yaml", proxy_mode="on")._setup_proxy(False)
    backend.update_subscription.assert_not_called()
    backend.start.assert_called_once()
    repair.assert_called_once_with(config, profile)


def test_bash_prompt_tracks_switch_preserves_hooks_and_is_idempotent(tmp_path):
    source = Path(policy.__file__).with_name("shell.bash")
    command = tmp_path / "autodl"
    state = tmp_path / "state"
    state.write_text("export https_proxy=http://127.0.0.1:7890\n")
    command.write_text('#!/bin/bash\ncat "' + str(state) + '"\n')
    command.chmod(0o700)
    script = '''
PROMPT_COMMAND=': original-hook'
source "$1"
source "$1"
[[ ${#PROMPT_COMMAND[@]} == 2 && ${PROMPT_COMMAND[0]} == ': original-hook' ]] || exit 1
[[ "$https_proxy" == http://127.0.0.1:7890 ]] || exit 2
printf 'unset https_proxy\n' > "$2"
false
_autodl_proxy_refresh
[[ $? == 1 && -z ${https_proxy+x} ]] || exit 3
'''
    env = dict(os.environ, PATH=str(tmp_path) + ":" + os.environ["PATH"])
    subprocess.run(["bash", "--noprofile", "--norc", "-c", script, "bash", str(source), str(state)], env=env, check=True)


def test_ssh_off_connects_directly(tmp_path):
    from src.lib.network import ssh_connect
    policy.write_mode("off", tmp_path / "config.yaml")
    with patch.object(ssh_connect.socket, "create_connection") as connect:
        ssh_connect.connect("github.com", 22, tmp_path / "config.yaml")
    connect.assert_called_once_with(("github.com", 22), timeout=15)

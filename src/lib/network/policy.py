"""Persistent proxy preference; inspection never starts networking or reads secrets."""
import json
import os
import shlex
import sys
import tempfile
from pathlib import Path

import yaml

from src.core.runtime import DEFAULT_CONFIG_FILE

PROXY_KEYS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
              "all_proxy", "ALL_PROXY", "no_proxy", "NO_PROXY")
NO_PROXY = "localhost,127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"


def read_mode(config_file: Path = DEFAULT_CONFIG_FILE) -> str:
    path = config_file.parent / "proxy-state.json"
    if not path.exists():
        return "auto"  # Preserve installations that have not opted into the switch.
    data = json.loads(path.read_text())
    if data.get("mode") not in ("on", "off"):
        raise ValueError(f"Invalid proxy mode in {path}")
    return data["mode"]


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".proxy-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def proxy_port() -> int:
    manifest = Path(__file__).parent / "proxy" / "manifest.yaml"
    return int(yaml.safe_load(manifest.read_text()).get("proxy_port", 7890))


def proxy_environment(url: str | None = None) -> dict[str, str]:
    url = url or f"http://127.0.0.1:{proxy_port()}"
    return {key: NO_PROXY if key.lower() == "no_proxy" else url for key in PROXY_KEYS}


def clear_proxy_environment() -> None:
    for key in PROXY_KEYS:
        os.environ.pop(key, None)


def shell_environment(config_file: Path = DEFAULT_CONFIG_FILE) -> str:
    """Proxy-only exports; never expose API tokens or subscription credentials."""
    mode = read_mode(config_file)
    if mode == "auto":
        return ""  # No ownership of the user's shell before explicit on/off.
    if mode == "off":
        return "unset " + " ".join(PROXY_KEYS)
    return "\n".join(f"export {key}={shlex.quote(value)}"
                     for key, value in proxy_environment().items())


def ssh_command(config_file: Path) -> str:
    connector = shlex.join([sys.executable, "-m", "src.lib.network.ssh_connect",
                           "--config-file", str(config_file), "%h", "%p"])
    return shlex.join(["ssh", "-o", "ProxyCommand=" + connector])


def write_mode(mode: str, config_file: Path = DEFAULT_CONFIG_FILE) -> None:
    if mode not in ("on", "off"):
        raise ValueError(mode)
    # This file is only used after an explicit `proxy install-git`.
    # Empty http.proxy disables even stale inherited proxy environment variables.
    url = f"http://127.0.0.1:{proxy_port()}" if mode == "on" else ""
    command = ssh_command(config_file) if mode == "on" else "ssh"
    git_config = f'[http]\n\tproxy = {json.dumps(url)}\n[core]\n\tsshCommand = {json.dumps(command)}\n'
    atomic_write(config_file.parent / "proxy.gitconfig", git_config)
    atomic_write(config_file.parent / "proxy-state.json", json.dumps({"mode": mode}) + "\n")

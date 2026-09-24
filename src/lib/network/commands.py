"""User-facing proxy controls, separate from read-only network diagnostics."""
import os
import shlex
import shutil
import socket
from datetime import datetime, timezone
from pathlib import Path

from src.core.adapters import SubprocessRunner
from src.core.runtime import DEFAULT_CONFIG_FILE
from src.lib.network.policy import (
    atomic_write, proxy_port, read_mode, shell_environment, write_mode,
)


def install_git(config_file: Path) -> None:
    runner = SubprocessRunner()
    include = str((config_file.parent / "proxy.gitconfig").resolve())
    current = runner.run(["git", "config", "--global", "--get-all", "include.path"], check=False)
    if include not in current.stdout.splitlines():
        # Don't hide another proxy or a custom SSH launcher behind our include.
        existing = runner.run(["git", "config", "--global", "--includes", "--name-only", "--get-regexp",
                               r"^(http\..*proxy|https\.proxy|core\.sshcommand)$"], check=False)
        if existing.stdout.strip():
            raise RuntimeError("已有 Git 代理或 SSH 配置，请先检查冲突；未覆盖。")
        if read_mode(config_file) == "auto":
            raise RuntimeError("请先执行 autodl proxy on 或 off")
        gitconfig = Path.home() / ".gitconfig"
        if gitconfig.exists():
            backup = gitconfig.with_name(".gitconfig.before-autodl-proxy-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
            shutil.copy2(gitconfig, backup)
            backup.chmod(0o600)
        runner.run(["git", "config", "--global", "--add", "include.path", include])
    print("Git HTTPS/SSH 已接入统一代理开关；仓库级自定义配置仍可能覆盖。")


def install_shell(config_file: Path) -> None:
    if config_file != DEFAULT_CONFIG_FILE:
        raise RuntimeError("Bash 集成仅使用默认配置路径")
    source = Path(__file__).with_name("shell.bash").resolve()
    wrapper = config_file.parent / "shell-proxy.bash"
    if wrapper.exists():
        old = wrapper.read_text()
        if not old.startswith(("# AutoDL managed shell proxy", "# Local Mihomo proxy environment")):
            raise RuntimeError(f"拒绝覆盖已有文件: {wrapper}")
    atomic_write(wrapper, "# AutoDL managed shell proxy\nsource " + shlex.quote(str(source)) + "\n")
    rc = Path.home() / ".bashrc"
    old = rc.read_text() if rc.exists() else ""
    if '.config/autodl-instance/shell-proxy.bash' not in old:
        if rc.exists():
            backup = rc.with_name(".bashrc.before-autodl-proxy-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
            shutil.copy2(rc, backup)
            backup.chmod(0o600)
        with rc.open("a") as stream:
            stream.write('\n# AutoDL managed shell proxy\nif [[ $- == *i* ]]; then\n    source "$HOME/.config/autodl-instance/shell-proxy.bash"\nfi\n')
    print("Bash 已接入统一开关；当前终端执行一次：source ~/.config/autodl-instance/shell-proxy.bash")


def dispatch(args) -> None:
    config_file = args.config_file
    action = args.proxy_command
    if action == "on":
        from src.lib.network.manager import NetworkManager
        # Only persist on after successful startup and an actual proxy request.
        NetworkManager(config_file, proxy_mode="on").setup()
        write_mode("on", config_file)
        print("代理已开启：Mihomo 已通过连通性检查。")
    elif action == "off":
        write_mode("off", config_file)
        print("代理已关闭：后续项目命令直连，不回退学术加速。")
        print("Mihomo 进程保留，避免中断已有连接；关闭使用代理与停止服务是两件事。")
    elif action == "env":
        print(shell_environment(config_file))
        return
    elif action == "status":
        from src.lib.network.proxy.base import ProxyConfig
        from src.lib.network.proxy.mihomo import MihomoBackend
        from src.lib.network.manager import _load_yaml, _PROXY_MANIFEST
        manifest = _load_yaml(_PROXY_MANIFEST)
        backend = MihomoBackend(ProxyConfig("", config_dir=(config_file.parent / "mihomo").resolve(),
                                          install_dir=Path(manifest.get("install_dir", "/usr/local/bin"))))
        mode = read_mode(config_file)
        print(f"代理开关: {mode}" + ("（尚未设置，沿用旧自动选择）" if mode == "auto" else ""))
        print(f"Mihomo 归属已验证的进程: {'运行中' if backend.is_running() else '未发现'}")
        try:
            with socket.create_connection(("127.0.0.1", proxy_port()), timeout=1):
                print(f"本地代理端口: 127.0.0.1:{proxy_port()} 可连接（未测试外网）")
        except OSError:
            print("本地代理端口: 不可连接")
        expected = f"http://127.0.0.1:{proxy_port()}"
        actual = [os.environ.get(key) for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")]
        print("当前调用环境: " + ("Mihomo" if all(v == expected for v in actual) else "无 HTTP 代理" if not any(actual) else "其他或不一致（值不显示）"))
        runner = SubprocessRunner()
        includes = runner.run(["git", "config", "--global", "--get-all", "include.path"], check=False).stdout.splitlines()
        print("Git 集成: " + ("已安装" if str((config_file.parent / "proxy.gitconfig").resolve()) in includes else "未安装"))
        return
    elif action == "install-git":
        install_git(config_file)
        return
    elif action == "install-shell":
        install_shell(config_file)
        return
    print("已接入的 Bash 在下次提示符同步；已运行的 ComfyUI 需重启，下载需重新发起。")

"""
bin/turbo CLI 入口

用法: eval $(python -m src.lib.network)
"""
import os
import sys

from src.lib.network.manager import export_env_shell


def main() -> None:
    output = export_env_shell()
    if output:
        print(output)
        # 输出 echo 语句让用户看到（stdout 被 eval 消费）
        proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
        if proxy:
            # 用 stderr 输出提示信息，避免被 eval 解析
            print(f"echo '[turbo] Proxy: {proxy}' >&2", flush=True)
        else:
            print("echo '[turbo] No proxy' >&2", flush=True)
    else:
        print("echo '[turbo] No network config found' >&2", flush=True)


if __name__ == "__main__":
    main()

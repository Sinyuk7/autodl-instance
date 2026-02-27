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
            print(f"echo '✓ 网络环境已就绪 (Proxy: {proxy})'")
        else:
            print("echo '✓ 网络环境已就绪 (无代理)'")
    else:
        print("echo '✗ 未检测到可用的网络配置'")


if __name__ == "__main__":
    main()

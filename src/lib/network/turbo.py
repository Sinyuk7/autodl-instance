"""
AutoDL 学术加速 - /etc/network_turbo 环境变量注入
"""
import logging
import os
import subprocess

from src.lib.network.config import AUTODL_TURBO_SCRIPT, AUTODL_TURBO_KEYS

logger = logging.getLogger("autodl_setup")


def load_autodl_turbo(verbose: bool = True) -> None:
    """加载 AutoDL 学术加速到当前进程环境变量

    优先级：
    1. 如果环境变量已设置（bash 脚本已 source），直接使用
    2. 否则尝试读取 /etc/network_turbo 并注入
    """
    # 检查是否已经由 shell 脚本设置 (bin/model 等会先 source)
    existing_proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
    if existing_proxy:
        if verbose:
            logger.info(f"  -> ✓ AutoDL 学术加速已启用 (Proxy: {existing_proxy})")
        return

    # 脚本不存在，跳过
    if not AUTODL_TURBO_SCRIPT.exists():
        if verbose:
            logger.info("  -> AutoDL 学术加速脚本不存在，跳过。")
        return

    # 尝试通过 subprocess 加载
    try:
        result = subprocess.run(
            ["bash", "-c", f"source {AUTODL_TURBO_SCRIPT} && env"],
            capture_output=True,
            text=True,
            check=True,
        )

        # 解析输出并注入环境变量
        injected = False
        for line in result.stdout.strip().split("\n"):
            if "=" in line:
                key, _, value = line.partition("=")
                if key in AUTODL_TURBO_KEYS:
                    os.environ[key] = value
                    injected = True

        if verbose:
            if injected:
                proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
                logger.info(f"  -> ✓ AutoDL 学术加速已启用 (Proxy: {proxy})")
            else:
                logger.info("  -> AutoDL 学术加速脚本未设置代理变量")

    except subprocess.CalledProcessError as e:
        if verbose:
            logger.warning(f"  -> [WARN] AutoDL 学术加速加载失败: {e}")
    except Exception as e:
        if verbose:
            logger.warning(f"  -> [WARN] 网络配置异常: {e}")

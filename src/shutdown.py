"""
AutoDL 关机同步脚本

执行所有插件的 sync() 方法（逆序），用于在关机前同步环境快照。
调用方式:
  - 直接执行: python -m src.shutdown
  - 通过 bye 命令: bye (需先执行 setup 生成 bin/ 脚本)
"""
import argparse
from pathlib import Path

from src.main import create_context, execute, BASE_DIR
from src.core.utils import logger, setup_logger
from src.lib.network import setup_network, stop_proxy


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoDL 关机同步")
    parser.add_argument("--debug", action="store_true", help="输出调试信息")
    args = parser.parse_args()

    # 初始化日志（必须在所有 logger 调用之前）
    log_file = BASE_DIR / "autodl-setup.log"
    setup_logger(log_file)

    # 初始化网络环境（sync 可能需要 git push 等网络操作）
    setup_network()

    logger.info("\n" + "=" * 50)
    logger.info(">>> AutoDL 关机同步 - 开始执行环境快照...")
    logger.info("=" * 50)
    
    # sync 需要加载 setup 阶段持久化的 artifacts
    context = create_context(debug=args.debug, load_artifacts=True)
    
    # 执行 sync 动作 (execute 内部会自动逆序执行)
    execute("sync", context)
    
    # 停止代理进程（如果有 mihomo 在运行）
    stop_proxy()

    logger.info("\n" + "=" * 50)
    logger.info("✅ 同步完成！您可以安全关闭机器了。")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
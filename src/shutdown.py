"""
AutoDL 关机同步脚本

执行所有插件的 sync() 方法（逆序），用于在关机前同步环境快照。
调用方式:
  - autodl bye
  - 兼容 shim: bye (需先执行 autodl setup 生成 bin/ 脚本)
"""
import argparse
from pathlib import Path

from src.main import create_context, execute
from src.core.runtime import resolve_runtime_config
from src.core.utils import logger, setup_logger
from src.lib.network import setup_network, stop_proxy, sync_proxy_config


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoDL 关机同步")
    parser.add_argument("--debug", action="store_true", help="输出调试信息")
    args = parser.parse_args()

    # 初始化日志（必须在所有 logger 调用之前）
    runtime = resolve_runtime_config(Path(__file__).resolve().parent.parent)
    runtime.workspace_dir.mkdir(parents=True, exist_ok=True)
    log_file = runtime.workspace_dir / "autodl-setup.log"
    setup_logger(log_file)

    # 初始化网络环境（sync 可能需要 git push 等网络操作）
    setup_network()

    logger.info("\n" + "=" * 50)
    logger.info(">>> AutoDL 关机同步 - 开始执行环境快照...")
    logger.info("=" * 50)
    
    # sync 需要加载 setup 阶段持久化的 artifacts
    context = create_context(debug=args.debug, load_artifacts=True)
    
    result = None
    try:
        sync_proxy_config()
        # 执行 sync 动作 (execute 内部会自动逆序执行)
        result = execute("sync", context)
    finally:
        # 停止代理进程（如果有 mihomo 在运行）
        stop_proxy()

    if result and result.warnings:
        logger.warning("\n>>> 同步完成，但有警告：")
        for issue in result.warnings:
            logger.warning(f"  -> [{issue.plugin}] {issue.message}")
            if issue.next_step:
                logger.warning(f"     下一步: {issue.next_step}")

    if result and not result.ok:
        logger.error("\n" + "=" * 50)
        logger.error("❌ 同步失败：请不要释放实例，除非确认本地数据不需要保留。")
        for issue in result.failures:
            logger.error(f"  -> [{issue.plugin}] {issue.message}")
            if issue.next_step:
                logger.error(f"     下一步: {issue.next_step}")
        logger.error("=" * 50)
        raise SystemExit(1)

    logger.info("\n" + "=" * 50)
    logger.info("✅ 同步完成！您可以安全关闭机器了。")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()

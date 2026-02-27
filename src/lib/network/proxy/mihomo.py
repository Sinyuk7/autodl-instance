"""
MihomoBackend - mihomo (Clash.Meta) 代理后端

精简主入口，组合 installer 和 config 子模块:
- 进程管理 (启动/停止/重启)
- 健康检查 (连通性测试)
- 配置热重载 (通过 RESTful API)
"""
import json
import logging
import os
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

from src.lib.network.proxy.base import ProxyBackend, ProxyConfig
from src.lib.network.proxy.installer import install_mihomo
from src.lib.network.proxy.config import download_subscription

logger = logging.getLogger("autodl_setup")

_PID_FILENAME = "mihomo.pid"
_LOG_FILENAME = "mihomo.log"


def _wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 10.0) -> bool:
    """等待端口可连接，用于确认 mihomo 启动完成"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False


def _wait_port_free(port: int, host: str = "127.0.0.1", timeout: float = 5.0) -> bool:
    """等待端口释放 (用于 stop 后重新 start)"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                time.sleep(0.5)  # 端口仍被占用
        except (ConnectionRefusedError, OSError):
            return True  # 端口已释放
    return False


class MihomoBackend(ProxyBackend):
    """mihomo (Clash.Meta) 代理后端"""

    @property
    def name(self) -> str:
        return "mihomo"

    @property
    def _bin_path(self) -> Path:
        return self.config.install_dir / "mihomo"

    @property
    def _config_file(self) -> Path:
        return self.config.config_dir / "config.yaml"

    @property
    def _pid_file(self) -> Path:
        return self.config.config_dir / _PID_FILENAME

    @property
    def _log_file(self) -> Path:
        return self.config.config_dir / _LOG_FILENAME

    # ── Install (委托 installer 模块) ───────────────────

    def install(self) -> bool:
        return install_mihomo(
            install_dir=self.config.install_dir,
            version=self.config.version,
        )

    # ── Subscription (委托 config 模块) ─────────────────

    def update_subscription(self) -> bool:
        return download_subscription(self.config, self._config_file)

    # ── Process Management ──────────────────────────────

    def start(self) -> bool:
        """启动 mihomo 后台进程

        日志输出到 config_dir/mihomo.log 便于排障。
        启动后通过端口探测确认进程就绪。
        """
        if not self._bin_path.exists():
            logger.error(f"  -> ✗ mihomo 内核不存在: {self._bin_path}")
            return False

        if not self._config_file.exists():
            logger.error(f"  -> ✗ 配置文件不存在: {self._config_file}")
            return False

        # 如果已经在运行，先停止
        if self.is_running():
            logger.info("  -> mihomo 已在运行，正在重启...")
            self.stop()
            _wait_port_free(self.config.proxy_port, timeout=5)

        logger.info("  -> 正在启动 mihomo...")

        try:
            # 确保配置目录存在 (日志文件需要)
            self.config.config_dir.mkdir(parents=True, exist_ok=True)

            # 日志输出到文件，便于排障
            log_f = open(self._log_file, "a", encoding="utf-8")

            process = subprocess.Popen(
                [
                    str(self._bin_path),
                    "-f", str(self._config_file),
                    "-d", str(self.config.config_dir),
                ],
                stdout=log_f,
                stderr=log_f,
                start_new_session=True,
            )

            # 记录 PID
            self._pid_file.write_text(str(process.pid))

            # 通过端口探测确认启动完成
            if not _wait_for_port(self.config.proxy_port, timeout=15):
                if process.poll() is not None:
                    # 进程已退出，输出日志帮助排障
                    log_tail = ""
                    try:
                        log_f.flush()
                        lines = self._log_file.read_text(encoding="utf-8").strip().splitlines()
                        log_tail = "\n".join(lines[-10:])  # 最后 10 行
                    except Exception:
                        pass
                    logger.error(
                        f"  -> ✗ mihomo 启动后退出 (code={process.returncode}), "
                        f"请查看日志: {self._log_file}"
                    )
                    if log_tail:
                        logger.error(f"  -> 日志尾部:\n{log_tail}")
                    return False
                logger.warning("  -> [WARN] mihomo 进程已启动但代理端口尚未就绪")

            logger.info(
                f"  -> ✓ mihomo 已启动 (PID: {process.pid}, "
                f"Proxy: {self.config.proxy_url})"
            )
            return True

        except Exception as e:
            logger.error(f"  -> ✗ mihomo 启动失败: {e}")
            return False

    def stop(self) -> bool:
        """停止 mihomo 进程 (仅通过 PID 精确停止，不使用 pkill)"""
        pid = self._read_pid()

        if pid is None:
            self._pid_file.unlink(missing_ok=True)
            logger.info("  -> mihomo 无 PID 记录，视为已停止")
            return True

        try:
            os.kill(pid, signal.SIGTERM)

            # 等待进程退出（最多 5 秒）
            for _ in range(10):
                time.sleep(0.5)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
            else:
                logger.warning(f"  -> [WARN] mihomo (PID: {pid}) SIGTERM 超时，强制 SIGKILL")
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

            self._pid_file.unlink(missing_ok=True)
            logger.info(f"  -> ✓ mihomo 已停止 (PID: {pid})")
            return True

        except ProcessLookupError:
            self._pid_file.unlink(missing_ok=True)
            logger.info("  -> mihomo 进程不存在，已清理 PID 文件")
            return True
        except Exception as e:
            logger.error(f"  -> ✗ 停止 mihomo 失败: {e}")
            return False

    def is_running(self) -> bool:
        """检查 mihomo 进程是否在运行"""
        pid = self._read_pid()
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    # ── Hot Reload ──────────────────────────────────────

    def reload(self) -> bool:
        """通过 RESTful API 热重载配置 (不重启进程)

        比 stop + start 更快，适合订阅更新后刷新配置。
        """
        if not self.is_running():
            logger.warning("  -> [WARN] mihomo 未运行，无法热重载")
            return False

        try:
            api_url = f"{self.config.api_url}/configs"
            data = json.dumps({"path": str(self._config_file)}).encode("utf-8")

            req = urllib.request.Request(
                api_url, data=data, method="PUT",
                headers={"Content-Type": "application/json"},
            )
            if self.config.api_secret:
                req.add_header("Authorization", f"Bearer {self.config.api_secret}")

            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status in (200, 204):
                    logger.info("  -> ✓ mihomo 配置已热重载")
                    return True

            return False
        except Exception as e:
            logger.warning(f"  -> [WARN] 热重载失败 (可尝试 restart): {e}")
            return False

    # ── Health Check ────────────────────────────────────

    def health_check(self) -> bool:
        """通过代理验证连通性

        使用 Cloudflare generate_204，比 Google 更快更稳定。
        """
        if not self.is_running():
            return False

        try:
            proxy_handler = urllib.request.ProxyHandler({
                "http": self.config.proxy_url,
                "https": self.config.proxy_url,
            })
            opener = urllib.request.build_opener(proxy_handler)

            req = urllib.request.Request(
                "https://cp.cloudflare.com/generate_204",
                method="GET",
            )
            resp = opener.open(req, timeout=10)
            return resp.status in (200, 204)

        except Exception:
            return False

    # ── Helpers ─────────────────────────────────────────

    def _read_pid(self) -> Optional[int]:
        """读取 PID 文件"""
        if not self._pid_file.exists():
            return None
        try:
            return int(self._pid_file.read_text().strip())
        except (ValueError, IOError):
            return None

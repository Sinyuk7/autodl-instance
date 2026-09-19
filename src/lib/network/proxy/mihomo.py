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

# Unix 信号常量 (Windows 上不存在，使用 getattr 安全获取)
_SIGTERM: int = getattr(signal, "SIGTERM", 15)
_SIGKILL: int = getattr(signal, "SIGKILL", 9)

from src.lib.network.proxy.base import ProxyBackend
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

        if not self._validate_config():
            return False

        # 如果已经在运行，先停止
        if self.is_running():
            logger.info("  -> mihomo 已在运行，正在重启...")
            if not self.stop():
                return False
            _wait_port_free(self.config.proxy_port, timeout=5)

        logger.info("  -> 正在启动 mihomo...")

        try:
            # 确保配置目录存在 (日志文件需要)
            self.config.config_dir.mkdir(parents=True, exist_ok=True)

            # Both paths are absolute and independent of the caller's cwd.
            with open(self._log_file, "a", encoding="utf-8") as log_f:
                process = subprocess.Popen(
                    [
                        str(self._bin_path.resolve()),
                        "-d", str(self.config.config_dir.resolve()),
                        "-f", str(self._config_file.resolve()),
                    ],
                    stdout=log_f,
                    stderr=log_f,
                    start_new_session=True,
                )

            # 记录 PID
            self._pid_file.write_text(str(process.pid))

            # Both listeners are part of the configured service contract.
            proxy_ready = _wait_for_port(self.config.proxy_port, timeout=15)
            api_ready = proxy_ready and _wait_for_port(self.config.api_port, timeout=5)
            if not (proxy_ready and api_ready):
                if process.poll() is not None:
                    logger.error(
                        f"  -> ✗ mihomo 启动后退出 (code={process.returncode}), "
                        f"请查看日志: {self._log_file}"
                    )
                else:
                    logger.error(
                        "  -> ✗ mihomo 进程存在但本地代理/API 端口未就绪，正在停止"
                    )
                    self.stop()
                return False

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
            os.kill(pid, 0)
        except ProcessLookupError:
            self._pid_file.unlink(missing_ok=True)
            logger.info("  -> mihomo 进程不存在，已清理 PID 文件")
            return True
        except PermissionError:
            logger.error(f"  -> ✗ 无权检查 mihomo PID: {pid}")
            return False

        if not self._process_matches(pid):
            logger.error(
                f"  -> ✗ PID {pid} 不属于当前 mihomo 配置，拒绝停止"
            )
            return False

        try:
            os.kill(pid, _SIGTERM)

            # 等待进程退出（最多 5 秒）
            for _ in range(10):
                time.sleep(0.5)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
            else:
                logger.error("mihomo SIGTERM timed out; refusing automatic SIGKILL")
                return False

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
        """检查 PID 是否仍是由当前绝对路径配置启动的 mihomo。"""
        pid = self._read_pid()
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
            return self._process_matches(pid)
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

        依次尝试多个测试端点，任一通过即可。
        优先使用 Google generate_204（最能代表代理是否真正工作），
        然后 Cloudflare，最后 Gstatic。
        """
        if not self.is_running():
            return False

        test_urls = [
            "https://www.google.com/generate_204",
            "https://cp.cloudflare.com/generate_204",
            "http://connectivitycheck.gstatic.com/generate_204",
        ]

        proxy_handler = urllib.request.ProxyHandler({
            "http": self.config.proxy_url,
            "https": self.config.proxy_url,
        })
        opener = urllib.request.build_opener(proxy_handler)

        for url in test_urls:
            try:
                req = urllib.request.Request(url, method="GET")
                resp = opener.open(req, timeout=10)
                if resp.status in (200, 204):
                    return True
            except Exception:
                continue

        return False

    # ── Helpers ─────────────────────────────────────────

    def _read_pid(self) -> Optional[int]:
        """读取 PID 文件"""
        if not self._pid_file.exists():
            return None
        try:
            pid = int(self._pid_file.read_text().strip())
            return pid if pid > 0 else None
        except (ValueError, IOError):
            return None

    def _validate_config(self) -> bool:
        """Run mihomo's config test with the exact production paths."""
        command = [
            str(self._bin_path.resolve()),
            "-t",
            "-d", str(self.config.config_dir.resolve()),
            "-f", str(self._config_file.resolve()),
        ]
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.error(f"  -> ✗ mihomo 配置检查无法执行: {exc}")
            return False
        if result.returncode != 0:
            logger.error(
                f"  -> ✗ mihomo 配置检查失败，请检查: {self._config_file}"
            )
            return False
        logger.info("  -> ✓ mihomo 配置检查通过")
        return True

    def _process_matches(self, pid: int) -> bool:
        """Verify executable and exact -d/-f arguments before managing a PID."""
        proc_dir = Path("/proc") / str(pid)
        try:
            executable = (proc_dir / "exe").resolve(strict=True)
            expected_executable = self._bin_path.resolve(strict=True)
            argv = (proc_dir / "cmdline").read_bytes().split(b"\0")
            arguments = [item.decode("utf-8", errors="surrogateescape") for item in argv if item]
        except (FileNotFoundError, OSError):
            return False

        expected_dir = str(self.config.config_dir.resolve())
        expected_file = str(self._config_file.resolve())

        def has_option(option: str, value: str) -> bool:
            return any(
                arguments[index] == option and arguments[index + 1] == value
                for index in range(len(arguments) - 1)
            )

        return (
            executable == expected_executable
            and has_option("-d", expected_dir)
            and has_option("-f", expected_file)
        )

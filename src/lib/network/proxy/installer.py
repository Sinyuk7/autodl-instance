"""
mihomo 内核安装器

职责:
- 检测系统架构
- 从 GitHub Releases 下载 mihomo 二进制
- SHA256 完整性校验
- 已安装版本检查（避免重复下载）
- 二进制可执行性验证
"""
import gzip
import hashlib
import logging
import platform
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("autodl_setup")

# ── 下载 URL 模板 ──────────────────────────────────────────
# 实际文件名格式: mihomo-linux-{arch}-{version}.gz
# 确认来源: https://github.com/MetaCubeX/mihomo/releases
_DOWNLOAD_URL = (
    "https://github.com/MetaCubeX/mihomo/releases/download"
    "/{version}/mihomo-linux-{arch}-{version}.gz"
)

# amd64 compatible 变体（不支持 AVX 的旧 CPU）
_DOWNLOAD_URL_COMPAT = (
    "https://github.com/MetaCubeX/mihomo/releases/download"
    "/{version}/mihomo-linux-amd64-compatible-{version}.gz"
)

# ── SHA256 校验表 ──────────────────────────────────────────
# 仅对常用架构/版本做预置，版本不在表中则跳过校验
_KNOWN_CHECKSUMS: Dict[str, Dict[str, str]] = {
    "v1.19.20": {
        "amd64": "631e9ec36a2f70d876bbe4c70f58c4fd99589584ace741bbc2240098f452ee3a",
        "amd64-compatible": "5e255e9eafd34077d177fc9c22b49c398c6a464b10b7bf3818f61e7179938de1",
        "arm64": "729b04fcf54a7be6dfbb138fe8a972e058c0d7f3fddc6206fd34443342121e7c",
    },
}


def detect_arch() -> str:
    """检测系统架构，映射到 mihomo 的命名

    Returns:
        mihomo Release 中使用的架构名 (amd64, arm64, ...)
    """
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "amd64"
    elif machine in ("aarch64", "arm64"):
        return "arm64"
    else:
        return machine


def _sha256_file(path: Path) -> str:
    """计算文件的 SHA256 摘要"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def check_installed_version(bin_path: Path, target_version: str) -> bool:
    """检查已安装的 mihomo 版本是否与目标版本一致

    Args:
        bin_path: mihomo 二进制路径
        target_version: 期望的版本字符串 (如 "v1.19.20")

    Returns:
        True 表示版本匹配
    """
    try:
        result = subprocess.run(
            [str(bin_path), "-v"],
            capture_output=True, text=True, timeout=5,
        )
        return target_version in result.stdout
    except Exception:
        return False


def _validate_binary(bin_path: Path) -> bool:
    """验证下载的二进制文件是否可正常执行"""
    try:
        result = subprocess.run(
            [str(bin_path), "-v"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and "mihomo" in result.stdout.lower()
    except Exception:
        return False


def install_mihomo(
    install_dir: Path,
    version: str,
    arch: Optional[str] = None,
) -> bool:
    """下载并安装 mihomo 内核二进制

    支持:
    - 版本校验: 已安装版本匹配则跳过
    - SHA256 校验: 常用架构/版本有预置校验值
    - 二进制验证: 解压后确认可执行

    Args:
        install_dir: 安装目录 (如 /usr/local/bin)
        version: 目标版本 (如 "v1.19.20")
        arch: 架构 (为 None 则自动检测)

    Returns:
        True 表示安装成功或已存在且版本匹配
    """
    if arch is None:
        arch = detect_arch()

    bin_path = install_dir / "mihomo"

    # 检查已安装版本
    if bin_path.exists():
        if check_installed_version(bin_path, version):
            logger.info(f"  -> ✓ mihomo 内核已存在且版本匹配: {bin_path}")
            return True
        else:
            logger.info("  -> 已安装版本不匹配，将重新下载...")
            bin_path.unlink(missing_ok=True)

    url = _DOWNLOAD_URL.format(version=version, arch=arch)

    logger.info(f"  -> 正在下载 mihomo {version} ({arch})...")
    logger.info(f"     URL: {url}")

    gz_path = install_dir / "mihomo.gz"

    try:
        install_dir.mkdir(parents=True, exist_ok=True)

        # 下载 .gz
        urllib.request.urlretrieve(url, str(gz_path))

        # SHA256 校验（如果该版本/架构有预置校验值）
        expected = _KNOWN_CHECKSUMS.get(version, {}).get(arch)
        if expected:
            actual = _sha256_file(gz_path)
            if actual != expected:
                raise RuntimeError(
                    f"SHA256 校验失败: 期望 {expected[:16]}..., "
                    f"实际 {actual[:16]}..."
                )
            logger.info("     SHA256 校验通过 ✓")

        # 解压
        with gzip.open(gz_path, "rb") as f_in:
            with open(bin_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        # 设置可执行权限
        bin_path.chmod(0o755)

        # 清理 .gz
        gz_path.unlink(missing_ok=True)

        # 验证二进制是否可执行
        if not _validate_binary(bin_path):
            raise RuntimeError("下载的二进制无法执行，文件可能损坏")

        logger.info(f"  -> ✓ mihomo 安装完成: {bin_path}")
        return True

    except Exception as e:
        logger.error(f"  -> ✗ mihomo 下载失败: {e}")
        # 清理残留
        gz_path.unlink(missing_ok=True)
        bin_path.unlink(missing_ok=True)
        return False

"""
Network Environment Manager - 网络环境统一管理

负责配置网络环境，确保所有插件/脚本的网络操作都能正常工作。

功能:
- AutoDL 学术加速 (/etc/network_turbo)
- HuggingFace 镜像 (HF_ENDPOINT)
- API Token 注入 (HF_TOKEN, CIVITAI_API_TOKEN)
- PyPI 镜像配置

配置来源:
- src/addons/system/manifest.yaml      (镜像配置)
- src/lib/download/secrets.yaml        (API Token)
"""
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import yaml

from src.core.schema import EnvKey

ENV_HF_TOKEN = EnvKey.HF_TOKEN
ENV_HF_ENDPOINT = EnvKey.HF_ENDPOINT
ENV_CIVITAI_TOKEN = EnvKey.CIVITAI_API_TOKEN

logger = logging.getLogger("autodl_setup")


class NetworkManager:
    """网络环境管理器"""
    
    # AutoDL 学术加速脚本路径
    AUTODL_TURBO_SCRIPT = Path("/etc/network_turbo")
    
    # AutoDL 学术加速设置的环境变量
    AUTODL_TURBO_KEYS = [
        "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", 
        "no_proxy", "NO_PROXY",
        "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"
    ]
    
    # 项目根目录
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

    def __init__(self) -> None:
        self._initialized = False

    def setup(self, verbose: bool = True) -> None:
        """初始化网络环境 (仅执行一次)
        
        Args:
            verbose: 是否输出日志，独立脚本可设为 False
        """
        if self._initialized:
            return
        
        if verbose:
            logger.info("\n>>> [Network] 正在初始化网络环境...")
        
        # 1. 加载 AutoDL 学术加速
        self._load_autodl_turbo(verbose)
        
        # 2. 加载 HuggingFace 镜像配置
        self._load_hf_mirror(verbose)
        
        # 3. 加载 API Token
        self._load_api_tokens(verbose)
        
        self._initialized = True

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """安全加载 YAML 文件"""
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _load_autodl_turbo(self, verbose: bool = True) -> None:
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
        if not self.AUTODL_TURBO_SCRIPT.exists():
            if verbose:
                logger.info("  -> AutoDL 学术加速脚本不存在，跳过。")
            return
        
        # 尝试通过 subprocess 加载
        try:
            result = subprocess.run(
                ["bash", "-c", f"source {self.AUTODL_TURBO_SCRIPT} && env"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # 解析输出并注入环境变量
            injected = False
            for line in result.stdout.strip().split("\n"):
                if "=" in line:
                    key, _, value = line.partition("=")
                    if key in self.AUTODL_TURBO_KEYS:
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

    def _load_hf_mirror(self, verbose: bool = True) -> None:
        """加载 HuggingFace 镜像配置"""
        # 如果已设置环境变量，跳过
        existing = os.environ.get(ENV_HF_ENDPOINT)
        if existing:
            if verbose:
                logger.info(f"  -> ✓ HF 镜像: {existing} (环境变量)")
            return
        
        # 从 system/manifest.yaml 读取配置
        system_config = self._load_yaml(self.PROJECT_ROOT / "src" / "addons" / "system" / "manifest.yaml")
        hf_mirror = system_config.get("huggingface_mirror")
        
        if hf_mirror and isinstance(hf_mirror, str):
            os.environ[ENV_HF_ENDPOINT] = hf_mirror
            if verbose:
                logger.info(f"  -> ✓ HF 镜像: {hf_mirror}")
        else:
            if verbose:
                logger.info("  -> ✗ HF 镜像: 未配置 (使用官方源，可能限速)")

    def _load_api_tokens(self, verbose: bool = True) -> None:
        """从 download/secrets.yaml 加载 API Token"""
        secrets_config = self._load_yaml(self.PROJECT_ROOT / "src" / "lib" / "download" / "secrets.yaml")
        
        api_keys_raw = secrets_config.get("api_keys", {})
        if not isinstance(api_keys_raw, dict):
            return
        api_keys = cast(Dict[str, Any], api_keys_raw)
        
        tokens_loaded: List[str] = []
        
        # HuggingFace Token (HF_TOKEN 是 huggingface_hub 官方标准)
        hf_token = api_keys.get("hf_api_token")
        if isinstance(hf_token, str) and hf_token:
            os.environ.setdefault(ENV_HF_TOKEN, hf_token)
            tokens_loaded.append(ENV_HF_TOKEN)
        
        # CivitAI Token
        civitai_token = api_keys.get("civitai_api_token")
        if isinstance(civitai_token, str) and civitai_token:
            os.environ.setdefault(ENV_CIVITAI_TOKEN, civitai_token)
            tokens_loaded.append(ENV_CIVITAI_TOKEN)
        
        if verbose and tokens_loaded:
            logger.info(f"  -> ✓ API Token 已加载: {', '.join(tokens_loaded)}")


# 全局单例
_network_manager: Optional[NetworkManager] = None


def setup_network(verbose: bool = True) -> None:
    """初始化网络环境 (全局入口)
    
    Args:
        verbose: 是否输出日志，main.py 中设为 True，独立脚本可设为 False
    """
    global _network_manager
    if _network_manager is None:
        _network_manager = NetworkManager()
    _network_manager.setup(verbose)


# ── 用于 bin/turbo 的环境变量导出 ───────────────────────────

# turbo 需要导出到用户 shell 的环境变量 key 列表
_EXPORT_KEYS = [
    # 代理
    "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
    "no_proxy", "NO_PROXY",
    "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE",
    # HuggingFace
    EnvKey.HF_ENDPOINT, EnvKey.HF_TOKEN,
    # CivitAI
    EnvKey.CIVITAI_API_TOKEN,
]


def export_env_shell() -> str:
    """执行 setup_network() 后，输出所有网络相关环境变量的 export 语句。
    
    供 bin/turbo 使用: eval $(python -m src.lib.network)
    这样 network.py 就是 bash 和 Python 两个世界的唯一真相来源。
    """
    setup_network(verbose=False)
    
    lines: List[str] = []
    for key in _EXPORT_KEYS:
        value = os.environ.get(key)
        if value:
            # 转义单引号，防止注入
            safe_value = value.replace("'", "'\\''")
            lines.append(f"export {key}='{safe_value}'")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # 被 bin/turbo 调用: eval $(python -m src.lib.network)
    output = export_env_shell()
    if output:
        print(output)
        # 输出到 stderr 让用户看到（stdout 被 eval 消费）
        proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
        if proxy:
            print(f"echo '✓ 网络环境已就绪 (Proxy: {proxy})'", file=sys.stdout)
        else:
            print("echo '✓ 网络环境已就绪 (无代理)'", file=sys.stdout)
    else:
        print("echo '✗ 未检测到可用的网络配置'", file=sys.stdout)

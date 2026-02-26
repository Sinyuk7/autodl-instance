"""
Schema & 类型定义

集中管理:
- StateKey: 状态持久化 Key 枚举（避免魔法字符串）
- EnvKey: 环境变量名枚举（避免魔法字符串）
"""
from enum import Enum


# ============================================================
# 状态持久化 Key（避免魔法字符串）
# ============================================================
class StateKey(str, Enum):
    """
    所有状态 Key 的枚举定义。
    
    命名规则: {ADDON_NAME}_{ACTION}
    """
    # SystemAddon
    SYSTEM_TOOLS_INSTALLED = "system_tools_installed"
    COMFY_CLI_INSTALLED = "comfy_cli_installed"
    
    # TorchAddon
    TORCH_INSTALLED = "torch_installed"
    
    # ComfyAddon
    COMFY_INSTALLED = "comfy_core_installed"
    
    # NodesAddon
    NODES_RESTORED = "nodes_restored"
    
    # UserdataAddon
    USERDATA_INITIALIZED = "userdata_initialized"
    
    # ModelAddon
    EXTRA_PATHS_CONFIGURED = "extra_paths_configured"


# ============================================================
# 环境变量名枚举（仅用于第三方库读取的环境变量）
# ============================================================
class EnvKey(str, Enum):
    """
    需要注入到 os.environ 的环境变量名。
    
    注意：仅收录第三方库通过 os.getenv() 读取的 Key。
    插件自身的配置应通过 manifest 显式传递。
    """
    # HuggingFace
    HF_TOKEN = "HF_TOKEN"
    HF_ENDPOINT = "HF_ENDPOINT"
    
    # CivitAI
    CIVITAI_API_TOKEN = "CIVITAI_API_TOKEN"
    
    # Proxy
    HTTP_PROXY = "http_proxy"
    HTTPS_PROXY = "https_proxy"
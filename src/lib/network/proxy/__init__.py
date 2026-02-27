"""
Proxy 子系统 - 代理内核管理

提供代理后端的抽象接口和具体实现。
当前默认: MihomoBackend (mihomo / Clash.Meta)
"""
from src.lib.network.proxy.base import ProxyBackend, ProxyConfig
from src.lib.network.proxy.mihomo import MihomoBackend

__all__ = ["ProxyBackend", "ProxyConfig", "MihomoBackend"]

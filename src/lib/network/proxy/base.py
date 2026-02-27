"""
ProxyBackend - 代理后端抽象接口

定义代理内核的统一操作契约，方便未来扩展不同内核（mihomo / sing-box / xray）。
当前默认实现: MihomoBackend
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ProxyConfig:
    """代理后端配置"""

    # 订阅地址
    subscription_url: str

    # 本地代理监听端口
    proxy_port: int = 7890

    # RESTful API 端口（用于节点切换、延迟测试等）
    api_port: int = 9090

    # API Secret（mihomo external-controller 认证）
    api_secret: str = ""

    # 内核版本
    version: str = "v1.19.20"

    # 内核安装目录
    install_dir: Path = Path("/usr/local/bin")

    # 配置文件目录
    config_dir: Path = Path("/etc/mihomo")

    @property
    def proxy_url(self) -> str:
        return f"http://127.0.0.1:{self.proxy_port}"

    @property
    def api_url(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"


class ProxyBackend(ABC):
    """代理后端抽象基类"""

    def __init__(self, config: ProxyConfig) -> None:
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """后端名称（如 mihomo, sing-box）"""
        ...

    @abstractmethod
    def install(self) -> bool:
        """下载并安装内核二进制

        Returns:
            True 表示安装成功或已存在
        """
        ...

    @abstractmethod
    def update_subscription(self) -> bool:
        """下载/更新订阅配置

        Returns:
            True 表示配置更新成功
        """
        ...

    @abstractmethod
    def start(self) -> bool:
        """启动代理进程

        Returns:
            True 表示启动成功
        """
        ...

    @abstractmethod
    def stop(self) -> bool:
        """停止代理进程

        Returns:
            True 表示停止成功
        """
        ...

    @abstractmethod
    def is_running(self) -> bool:
        """检查代理进程是否在运行"""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """验证代理是否可用（实际发请求测试连通性）"""
        ...

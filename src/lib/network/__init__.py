"""
Network Environment Manager - 网络环境统一管理

负责配置网络环境，确保所有插件/脚本的网络操作都能正常工作。

模块结构:
- config.py       配置常量（路径、Key、导出列表）
- turbo.py        AutoDL 学术加速（/etc/network_turbo，兜底方案）
- mirror.py       镜像源管理（HF_ENDPOINT 等）
- token.py        API Token 管理（HF_TOKEN, CIVITAI_API_TOKEN）
- manager.py      核心编排器（NetworkManager, setup_network）
- proxy/          代理子系统（mihomo 内核管理、订阅更新）

代理策略:
  有 proxy/secrets.yaml 且配置了 subscription_url → mihomo 代理
  没有 → fallback 到 AutoDL 学术加速（/etc/network_turbo）

配置来源:
- src/lib/network/proxy/manifest.yaml   (代理技术参数)
- src/lib/network/proxy/secrets.yaml    (代理订阅地址，不提交 git)
- src/addons/system/manifest.yaml       (镜像配置)
- src/lib/download/secrets.yaml         (API Token)
"""
from src.lib.network.manager import setup_network, export_env_shell, stop_proxy

__all__ = ["setup_network", "export_env_shell", "stop_proxy"]
"""
Network Environment Manager - 网络环境统一管理

负责配置网络环境，确保所有插件/脚本的网络操作都能正常工作。

模块结构:
- config.py       配置常量（路径、Key、导出列表）
- turbo.py        AutoDL 学术加速（/etc/network_turbo）
- mirror.py       镜像源管理（HF_ENDPOINT 等）
- token.py        API Token 管理（HF_TOKEN, CIVITAI_API_TOKEN）
- manager.py      核心编排器（NetworkManager, setup_network）
- proxy/          代理子系统（代理池、健康检查、节点订阅）
- diagnostics.py  网络诊断（连通性测试、延迟检测）

配置来源:
- src/addons/system/manifest.yaml      (镜像配置)
- src/lib/download/secrets.yaml        (API Token)
"""
from src.lib.network.manager import setup_network, export_env_shell

__all__ = ["setup_network", "export_env_shell"]

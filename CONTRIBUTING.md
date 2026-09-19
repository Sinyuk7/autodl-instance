# 开发说明

源码放在 /root/autodl-instance，使用 README 中的 editable 安装。不要修改 AutoDL 基础 Conda/Jupyter 环境或 NVIDIA 驱动。

- 安装与启动固定使用配置的 python_env_dir，默认 /root/.venvs/comfyui。
- 插件顺序固定：system → comfy_core。Torch 由 comfy-cli 安装，不单独锁版本。
- init 每次开机检查挂载、补目录、建立安全链接和初始化代理；setup 只安装环境；migrate 显式搬迁数据并保留冲突，不建立链接；下载按需初始化网络。
- 帮助、status、doctor、模型列表必须只读，不能启动服务。
- 模型、输出使用共享存储；downloads/cache/temp 使用本地盘。写入前验证挂载。
- 配置在 ~/.config/autodl-instance/config.yaml；秘密在同目录 secrets.yaml，权限 600。
- Mihomo 配置在同目录 mihomo/config.yaml。不要把秘密写入 Git 或数据盘。
- 子进程通过 ctx.cmd 调用；文件迁移保留冲突；停止进程必须确认归属，只自动发送 SIGTERM。
- 不自动修改 shell 启动文件。可执行入口只维护 autodl。

运行 `pytest tests/ -q`。测试必须使用临时目录和模拟安装器/网络，不启动真实服务，不读取主机秘密。新增测试应覆盖实际失败路径和安全边界。

# 插件测试

运行 `pytest tests/unit/addons/ -q`。

system 验证工具和独立环境；comfy_core 验证依赖统一安装到独立环境；
comfy_core 验证同一 venv 的安装与启动；workspace/models 验证迁移、冲突保留和软链接。
所有安装命令使用 MockRunner。

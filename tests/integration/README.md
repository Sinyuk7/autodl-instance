# 集成测试

运行 `pytest tests/integration/ -q`。

测试用临时目录承载 ComfyUI、venv 和数据，模拟外部命令。
完整 setup 验证插件之间的数据传递、模型和 user 文件保留、output/models 软链接及 artifacts 持久化。
真实 GPU、联网安装和公网访问不在这些隔离测试范围内。

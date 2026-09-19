# 集成测试

运行 `pytest tests/integration/ -q`。

测试用临时目录承载 ComfyUI、venv 和数据，模拟外部命令。
完整 setup 验证安装插件之间的数据传递、原目录和文件保持不变、无数据软链接及 artifacts 持久化。init/migrate 的临时目录测试覆盖链接幂等性、拒绝覆盖和冲突保留。
真实 GPU、联网安装和公网访问不在这些隔离测试范围内。

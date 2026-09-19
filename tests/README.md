# 测试

```bash
pytest tests/ -q
pytest tests/unit/ -q
pytest tests/integration/ -q
```

单元测试覆盖配置、CLI、环境选择、下载预检与路径、文件迁移和进程归属。
集成测试使用真实插件顺序、MockRunner 和临时目录，验证迁移及 artifacts。
它们不会验证真实模型下载、CUDA 推理或 AutoDL 公网映射。

测试隔离进程环境变量和本机秘密。不要把真实 setup/start/stop 当作测试探针。

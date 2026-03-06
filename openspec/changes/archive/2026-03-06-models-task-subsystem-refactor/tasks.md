## 1. 基础设施准备

- [ ] 1.1 确认 `src/core/task.py` 已存在（从 task-subsystem-refactor 引入）
- [ ] 1.2 确认 `src/core/interface.py` 已扩展 `get_tasks()` 方法
- [ ] 1.3 如需扩展，参考 torch_engine 重构经验

## 2. ModelAddon 重构

- [ ] 2.1 创建 `src/addons/models/tasks/__init__.py` 目录
- [ ] 2.2 实现 SetupModelsSymlinkTask（priority=10）
- [ ] 2.3 实现 MigrateExistingModelsTask（priority=20）
- [ ] 2.4 实现 CheckOrphanFilesTask（priority=10）
- [ ] 2.5 实现 CleanupOrphanMetasTask（priority=20）
- [ ] 2.6 实现 GenerateSnapshotTask（priority=30）
- [ ] 2.7 重构 `plugin.py` 使用 TaskRunner
- [ ] 2.8 更新 `manifest.yaml` 添加 Task 配置

## 3. 验证测试

- [ ] 3.1 运行 `python -m src.main setup --only models` 验证 Task 执行
- [ ] 3.2 运行 `python -m src.main sync --only models` 验证 Task 执行
- [ ] 3.3 验证日志输出符合扁平风格
- [ ] 3.4 验证 Task 可独立禁用

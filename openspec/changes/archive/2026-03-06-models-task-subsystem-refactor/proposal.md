## Why

当前 `ModelAddon` 的 `setup()` 和 `sync()` 方法包含多个独立功能逻辑混杂在一起，缺乏细粒度的任务拆分和配置灵活性。随着模型管理功能增加（如新增下载策略、模型分类验证等），代码会持续膨胀，修复逻辑难以独立控制。

**为什么是现在**：
- 与 `task-subsystem-refactor` proposal 已有完整的 Task 架构设计（`BaseTask`、`TaskRunner`）
- `ModelAddon` 是候选迁移插件之一（P2 优先级），结构清晰适合作为第二个迁移目标
- 可复用到已有的 `torch_engine` 迁移经验

## What Changes

1. **引入 Task 子系统**：为 `ModelAddon` 引入 `BaseTask` + `TaskRunner` 架构
2. **拆分 Setup 阶段**：将 `setup()` 拆分为 `SetupModelsSymlinkTask` + `MigrateExistingModelsTask`
3. **拆分 Sync 阶段**：将 `sync()` 拆分为 `CheckOrphanFilesTask` + `CleanupOrphanMetasTask` + `GenerateSnapshotTask`
4. **配置驱动**：通过 `manifest.yaml` 支持独立启用/禁用单个 Task
5. **内部幂等**：每个 Task 自行检测环境状态，决定是否执行修复

## Capabilities

### New Capabilities
- `models-task-subsystem`: 将 ModelAddon 重构为 Task 架构
  - `models-symlink-task`: Setup 阶段软链接管理 Task
  - `models-migration-task`: 现有模型文件迁移 Task  
  - `models-orphan-check-task`: Sync 阶段残留文件检查 Task
  - `models-meta-cleanup-task`: 孤儿 .meta 文件清理 Task
  - `models-snapshot-task`: 模型快照生成 Task

### Modified Capabilities
- 无（现有能力保持不变，仅重构实现方式）

## Impact

- **代码变更**：`src/addons/models/plugin.py` 重构为 Task 驱动
- **新增文件**：`src/addons/models/tasks/` 目录存放独立 Task 实现
- **配置变更**：`src/addons/models/manifest.yaml` 添加 Task 开关配置
- **执行顺序**：不受影响，仍在 `NodesAddon` 之后执行
- **兼容性**：`ModelAddon` 对外接口不变，不影响上下游 Addon

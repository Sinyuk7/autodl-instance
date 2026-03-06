## Context

当前 `ModelAddon` 的 `setup()` 和 `sync()` 方法各自包含多个独立功能的代码块：
- `setup()`: 软链接创建 + 现有模型迁移
- `sync()`: 残留文件检查 + 清理孤儿 .meta + 生成快照

随着功能增加，这些方法会持续膨胀，修复逻辑难以独立控制。

## Goals / Non-Goals

**Goals:**
1. 引入 Task 子系统架构（BaseTask + TaskRunner）
2. 将 `setup()` 拆分为独立 Task：软链接管理 + 模型迁移
3. 将 `sync()` 拆分为独立 Task：残留文件检查 + 清理 + 快照生成
4. 支持通过 manifest.yaml 配置独立启用/禁用 Task
5. 保证每个 Task 内部幂等（自行检测环境状态）

**Non-Goals:**
- 不修改模型存储的实际逻辑（软链接目标、存储路径不变）
- 不修改 downloader 逻辑（下载器独立于 Addon）
- 不添加新的模型管理能力（仅重构）

## Addon Lifecycle Impact

| Phase | Affected Addons | Impact |
|-------|-----------------|--------|
| setup | ModelAddon | 重构为 TaskRunner.run_tasks() |
| start | 无 | 无变化 |
| sync  | ModelAddon | 重构为 TaskRunner.run_tasks() |

## Artifacts Contract

| Field | Type | Producer Addon | Consumer Addons |
|-------|------|----------------|-----------------|
| models_dir | Path | ModelAddon | (下游 Addon 读取，如需要) |

**说明**: Artifacts 无变更，仅重构内部实现方式。

## Task Definition

| Task Class | Priority | Returns |
|------------|----------|---------|
| SetupModelsSymlinkTask | 10 | SKIPPED: 已是正确软链接 / SUCCESS: 创建成功 / FAILED: 权限错误 |
| MigrateExistingModelsTask | 20 | SKIPPED: 无需迁移 / SUCCESS: 迁移完成 / FAILED: IO 错误 |
| CheckOrphanFilesTask | 10 | SKIPPED: 无残留文件 / SUCCESS: 迁移完成 / FAILED: IO 错误 |
| CleanupOrphanMetasTask | 20 | SKIPPED: 无孤儿 meta / SUCCESS: 清理完成 / FAILED: IO 错误 |
| GenerateSnapshotTask | 30 | SKIPPED: 目录为空 / SUCCESS: 快照生成 / FAILED: IO 错误 |

## Decisions

**Decision 1: Task 文件组织**
采用混合模式 - 简单 Task 内联在 plugin.py，复杂 Task 独立文件于 tasks/ 目录。

**Decision 2: 幂等策略**
所有 Task 采用内部幂等策略，通过检测物理文件系统状态自行判断是否需要执行。

**Decision 3: Task 划分粒度**
Setup 阶段按"创建链接"和"迁移数据"划分为两个 Task；Sync 阶段按"检查残留"、"清理meta"、"生成快照"划分为三个 Task。

## Risks / Trade-offs

**低风险变更，无需特殊处理**

- 纯内部重构，不影响外部接口
- 复用已有的 task-subsystem 基础设施
- 与 torch_engine 重构采用相同模式

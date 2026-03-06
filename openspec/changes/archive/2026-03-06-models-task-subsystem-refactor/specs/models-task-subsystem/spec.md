## ADDED Requirements

### Requirement: Setup 阶段软链接管理
ModelAddon 在 setup 阶段 SHALL 管理 ComfyUI/models/ 软链接，确保指向数据盘 autodl-tmp/models/。

#### Scenario: 软链接已正确存在
- **WHEN** ComfyUI/models/ 已是正确软链接（指向 autodl-tmp/models/）
- **THEN** Task 返回 SKIPPED，不执行任何操作

#### Scenario: 软链接指向错误位置
- **WHEN** ComfyUI/models/ 软链接存在但指向错误目标
- **THEN** 删除错误链接，创建正确软链接，返回 SUCCESS

#### Scenario: ComfyUI/models/ 是物理目录
- **WHEN** ComfyUI/models/ 是物理目录（非软链接）
- **THEN** 迁移目录内容到 autodl-tmp/models/，删除原目录，创建软链接，返回 SUCCESS

### Requirement: 现有模型文件迁移
ModelAddon SHALL 在 setup 阶段迁移 ComfyUI 原生目录中的现有模型文件到数据盘。

#### Scenario: 无需迁移
- **WHEN** ComfyUI/models/ 已是正确软链接，无残留文件
- **THEN** Task 返回 SKIPPED

#### Scenario: 需要迁移
- **WHEN** ComfyUI/models/ 是物理目录且包含模型文件
- **THEN** 递归迁移所有文件到目标目录，跳过冲突文件，返回 SUCCESS 并记录迁移数量

### Requirement: Sync 阶段残留文件检查
ModelAddon 在 sync 阶段 SHALL 检查并迁移可能残留在 ComfyUI 物理目录中的文件。

#### Scenario: 软链接正常
- **WHEN** ComfyUI/models/ 是正确软链接
- **THEN** Task 返回 SKIPPED，不执行任何操作

#### Scenario: 软链接断开变为物理目录
- **WHEN** ComfyUI/models/ 曾是软链接但已断开，变成物理目录
- **THEN** 迁移残留文件到目标目录，重建软链接，返回 SUCCESS

### Requirement: 孤儿 .meta 文件清理
ModelAddon SHALL 在 sync 阶段清理孤儿 .meta sidecar 文件。

#### Scenario: 无孤儿文件
- **WHEN** 所有 .meta 文件都有对应的模型文件
- **THEN** Task 返回 SKIPPED

#### Scenario: 存在孤儿 .meta 文件
- **WHEN** 存在无对应模型文件的 .meta sidecar
- **THEN** 删除孤儿 .meta 文件，返回 SUCCESS 并记录清理数量

### Requirement: 模型快照生成
ModelAddon SHALL 在 sync 阶段扫描模型目录，生成 model-lock.yaml 快照。

#### Scenario: 模型目录为空
- **WHEN** autodl-tmp/models/ 目录为空或不存在的模型子目录
- **THEN** Task 返回 SKIPPED，不写入 lock 文件

#### Scenario: 正常生成快照
- **WHEN** 模型目录包含有效模型文件
- **THEN** 生成快照（包含路径、哈希、类型、来源），写入 model-lock.yaml，返回 SUCCESS

# RFC-005: 节点版本锁定与快照边界提示

## 背景

`src/addons/nodes/manifest.yaml` 只记录节点 Git URL，安装时 `git clone --depth 1` 默认拉最新分支。ComfyUI-Manager snapshot 可以恢复节点，但官方 README 也说明非 Git 节点支持不完整。节点版本漂移会导致换实例后 workflow 行为变化。

## 用户价值

Job-to-be-done：新实例恢复后节点行为尽量一致。触达频率不高，但一旦节点升级破坏 workflow，排查成本很高。

## 提议

MVP：
- `nodes sync` 额外生成 `nodes-lock.yaml`，记录每个 `custom_nodes/*` 的 remote URL、current commit、dirty 状态。
- `nodes setup` 如果 snapshot 不可用或失败，manifest 安装支持 `ref` 字段。
- `doctor` 检测 manifest URL 与本地 remote 是否一致、是否 dirty、是否 detached。

## 非目标

- 不 fork 或托管第三方节点。
- 不自动回滚节点。
- 不替代 ComfyUI-Manager snapshot。

## 替代方案

方案 A：完全依赖 Manager snapshot。简单，但边界不透明。

方案 B：manifest 手写每个 commit。准确但维护负担大。

本方案先自动生成 lock，再让 manifest 可选 pin。

## 影响面

- `src/addons/nodes/plugin.py`
- `src/addons/nodes/manifest.yaml` schema/comment
- `my-comfyui-backup/nodes-lock.yaml`
- tests for lock generation

不新增依赖，只调用 Git。

## 风险

- Git 仓库很多时 sync 变慢。
- 部分节点目录不是 Git repo，应标 SKIP。

## 验收标准

- `bye` 后生成 lock，包含至少 URL/commit/dirty。
- 新实例无 snapshot 时能按 manifest `ref` clone/checkout。
- dirty 节点在 `doctor` 中明确提示不会被自动保存。

## RICE

Reach 1/week, Impact 5, Confidence 0.75, Effort 2.0d => 1.9

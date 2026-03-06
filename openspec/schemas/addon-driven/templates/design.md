## Context

<!-- 
变更的背景和动机。
说明当前状态、问题根源、以及为什么需要这个变更。
-->

## Goals / Non-Goals

**Goals:**
<!-- 此设计要达成的目标，保持简洁（3-5 条） -->

**Non-Goals:**
<!-- 明确排除的范围，避免 scope creep -->

## Addon Lifecycle Impact

<!-- 
此变更对 Addon 生命周期各阶段的影响。
如果某阶段无影响，填 "无" 或省略该行。
-->

| Phase | Affected Addons | Impact |
|-------|-----------------|--------|
| setup | | |
| start | | |
| sync  | | |

## Artifacts Contract

<!-- 
新增或修改的 Artifacts 字段。
明确 Producer（谁设置）和 Consumer（谁读取）的关系。
如无变更，填 "无 Artifacts 变更"。
-->

| Field | Type | Producer Addon | Consumer Addons |
|-------|------|----------------|-----------------|
| | | | |

## Task Definition

<!-- 
如涉及新 Task 或修改现有 Task，列出定义。
如无 Task 变更，填 "无 Task 变更"。

示例:
| Task Class | Priority | Returns |
|------------|----------|---------|
| ValidateCudaTask | 10 | SKIPPED: CUDA 已就绪 / SUCCESS: 安装成功 / FAILED: 驱动不兼容 |
-->

## Decisions

<!-- 
关键技术决策及理由。
每个决策单独成段，包含：
- Decision N: 标题
- 变更内容
- 理由/权衡
-->

## Risks / Trade-offs

<!-- 
已知风险、权衡、以及缓解措施。
如无明显风险，可简述 "低风险变更，无需特殊处理"。
-->
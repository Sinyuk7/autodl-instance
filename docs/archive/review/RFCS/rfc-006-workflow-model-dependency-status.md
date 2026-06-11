# RFC-006: workflow 模型依赖状态（best-effort）

## 背景

项目当前能列已下载模型和 preset，但不能从 workflow 角度回答“这个 workflow 还缺哪些模型”。`comfy-cli` 已支持 workflow 节点依赖检查，模型依赖仍需要基于常见节点字段做 best-effort 分析。

## 用户价值

Job-to-be-done：用户打开某个 workflow 前，知道模型是否齐全。日常启动和新实例恢复都会触达；没有它时要等 ComfyUI 报错。

## 提议

MVP：
- `model status --workflow <file>` 解析常见节点的 `widgets_values`/inputs，覆盖 Checkpoint/UNET/VAE/CLIP/LoRA 等内置和常见节点。
- 输出 found/missing/unknown 三类。
- 未识别节点只提示 unknown，不失败。
- 可选把 workflow 中发现的模型名与 lock path 做模糊匹配。

## 非目标

- 不自动下载。
- 不承诺 100% 精确。
- 不实现通用 ComfyUI 节点 schema 引擎。

## 替代方案

方案 A：只支持 preset。准确但要求用户维护 preset。

方案 B：运行 ComfyUI API 做动态验证。更准但需要服务启动，占 GPU/环境。

本方案作为离线 best-effort 辅助，不替代 preset。

## 影响面

- `src/addons/models/downloader.py`
- 新增 `src/addons/models/workflow_scan.py`
- README
- workflow fixture tests

不新增依赖，使用 `json`。

## 风险

- 节点格式差异大，误报不可避免。
- 输出必须清楚区分“确认缺失”和“无法判断”。

## 验收标准

- 对 example workflow 能列出至少常见模型引用。
- 缺失模型能和本地 models 目录对比。
- 对未知节点不抛异常。

## RICE

Reach 3/week, Impact 5, Confidence 0.6, Effort 3.0d => 3.0

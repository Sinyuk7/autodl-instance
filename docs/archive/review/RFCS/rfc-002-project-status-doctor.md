# RFC-002: 新增 status / doctor 健康检查

## 背景

当前用户只能运行 `start` 后由 ComfyUI 或 workflow 报错。软链接、磁盘空间、Git 推送、网络代理、节点快照、模型缺失都没有统一入口。

## 用户价值

Job-to-be-done：在开始占用 GPU 前确认工作区是否可用。高频在日常启动、新实例恢复、关机前触达；没有它时失败成本高。

## 提议

MVP：
- 新增 `status`：快速显示数据盘、ComfyUI、userdata repo、models symlink、latest snapshot、model lock 三态摘要。
- 新增 `doctor`：执行更慢的深度检查，包括 Git remote、network fallback、HF mirror/token、磁盘余量、节点依赖、hash 校验抽样。
- 每条失败输出“出了什么、可能原因、下一步命令”。

## 非目标

- 不自动修复所有问题。
- 不引入 Web UI。
- 不阻断 `start`，除非用户显式 `--strict`。

## 替代方案

方案 A：把检查嵌入 `start`。更省命令，但启动噪声大且无法独立排障。

方案 B：只做 README 故障排查。维护便宜，但无法反映真实状态。

本方案保留独立 CLI，并让 `start` 只复用摘要提示。

## 影响面

- `src/main.py` 命令集合或新增 `src/status.py`
- `src/addons/*` 暴露只读检查函数
- README 快捷命令
- 单元测试 + mock command tests

不新增运行时依赖。

## 风险

- 检查项过多会让输出吓人；需要分 P0/P1/P2。
- 网络检查可能慢；`status` 必须快，`doctor` 可慢。

## 验收标准

- 无模型、无 userdata repo、无 proxy 配置时能给出清晰 SKIP，而不是失败。
- 破坏 `ComfyUI/models` 软链后 `status` 能检测。
- Git push 权限失效时 `doctor` 给出 SSH/key 下一步。

## RICE

Reach 5/week, Impact 5, Confidence 0.85, Effort 2.0d => 10.6

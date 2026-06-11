# RFC-004: cache 迁移澄清与磁盘预检

## 背景

README 声称 `.cache` 会迁移至数据盘，但 `SystemAddon` 没有实现；HF docs 默认 cache 在 `~/.cache/huggingface`。同时模型下载前没有磁盘余量预检，下载 5-30GB 模型时失败成本高。

## 用户价值

Job-to-be-done：在系统盘/数据盘容量有限时避免中途爆盘。模型下载触达低频但痛感高；cache 爆系统盘会破坏整个实例体验。

## 提议

MVP：
- 先修文档：如暂不迁移 `.cache`，README 删除承诺。
- `model download` 在开始前尝试读取文件大小；已知大小时检查目标盘剩余空间。
- `doctor` 检查 `~/.cache/huggingface`, `~/.cache/torch`, `~/.cache/uv` 大小并提示可选迁移。
- 后续可选实现 `cache link --target /root/autodl-tmp/cache`，由用户显式触发。

## 非目标

- 不默认迁移全部 `~/.cache`。
- 不自动删除用户 cache。
- 不引入磁盘管理服务。

## 替代方案

方案 A：默认软链整个 `~/.cache`。省心但风险大，可能影响已有工具和权限。

方案 B：只改 README。成本最低，但不能减少下载失败。

本方案先修文档，下载前做安全预检，迁移保持显式。

## 影响面

- README
- `src/addons/models/downloader.py`
- `src/lib/download/*`
- `doctor` 检查项
- tests for disk-preflight behavior

不新增依赖。

## 风险

- 很多 URL 无法提前拿到准确大小；输出应标为 best-effort。
- HuggingFace/CivitAI 重定向可能需要 token 才能获取 Content-Length。

## 验收标准

- README 不再承诺未实现的 `.cache` 自动迁移。
- 已知 Content-Length 大于可用空间时，下载前阻止并提示释放/扩容。
- 未知大小时继续下载但提示风险。

## RICE

Reach 2/week, Impact 5, Confidence 0.85, Effort 1.5d => 5.7

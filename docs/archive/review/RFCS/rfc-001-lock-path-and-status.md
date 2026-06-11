# RFC-001: 统一 model-lock 路径并增强 status

## 背景

`GenerateSnapshotTask._get_lock_file_path()` 写 `/root/autodl-tmp/model-lock.yaml`，但 `src/addons/models/config.py:LOCK_FILE` 读 `PROJECT_ROOT / "my-comfyui-backup" / "model-lock.yaml"`，`model status` 因此读不到 sync 产物。同时 `GenerateSnapshotTask` 复制了 `lock.py` 的扫描逻辑，且没有合并 `.meta` 中的 URL/source。

## 用户价值

Job-to-be-done：新实例恢复后，用户先知道“以前有哪些模型，现在缺哪些”。每次实例释放/迁移都会触达；没有它时只能靠记忆或 workflow 报错。收益是避免 GPU 时间浪费和重复查链接。

## 提议

MVP：
- 统一 lock 路径为 `my-comfyui-backup/model-lock.yaml`。
- `GenerateSnapshotTask` 只调用 `src.addons.models.lock.generate_snapshot()`。
- `model status` 显示三态：存在且 hash 一致、存在但 hash 漂移、lock 有但本地缺失。
- 缺失项如果有 URL，输出建议 `model download <url>`；无 URL 时提示手工定位来源。

## 非目标

- 不从 lock 自动下载模型。
- 不把 lock 变成下载任务表。
- 不把模型文件写入 Git。

## 替代方案

方案 A：只改读取路径到 `/root/autodl-tmp/model-lock.yaml`。成本最低，但跨实例不可见，违背核心原则。

方案 B：在 sync 末尾复制一份 lock 到 `my-comfyui-backup/`。能工作但保留双源真相。

本方案选择单一路径和单一生成逻辑。

## 影响面

- `src/addons/models/tasks/generate_snapshot.py`
- `src/addons/models/config.py`
- `src/addons/models/downloader.py`
- `tests/unit/addons/test_models_lock.py`
- 新增/修改 sync/status 测试

不新增依赖；用户会看到更明确的 `model status` 输出。

## 风险

- 旧的 `/root/autodl-tmp/model-lock.yaml` 需要一次性迁移或兼容读取。
- 如果用户未配置 `userdata_repo`，lock 仍只存在本地 `my-comfyui-backup/`，需要提示。

## 验收标准

- `bye` 后 `my-comfyui-backup/model-lock.yaml` 被写入。
- `model status` 能读到同一个 lock。
- lock 中包含 `.meta` 的 `url`/`source`。
- 删除一个本地模型后，`model status` 显示缺失和建议命令。

## RICE

Reach 4/week, Impact 10, Confidence 0.9, Effort 1.0d => 36.0

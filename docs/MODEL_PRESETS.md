# 模型目录与复制预设

固定两个模型根目录，同一类别内相对路径一致：

- tmp：`/root/autodl-tmp/ComfyUI/models/`
- fs：`/root/autodl-fs/models/`

ComfyUI 启动时读取 `extra_model_paths.yaml`，标准模型加载器优先查 tmp，再查 fs。
同相对路径两边都有时选择 tmp；tmp 不必包含完整模型库。
`init` 在 ComfyUI 已安装时写入固定配置；首次 `setup` 安装完成后也会补齐配置。
仅 tmp 设置 `is_default: true`，fs 不设置，作为后备目录。注册日志顺序不是最终查找顺序；应检查运行时路径列表。ComfyUI 自带及用户目录仍保留。
复制和下载不修改搜索配置。修改配置后需要重启 ComfyUI。

## 预设只负责复制

默认预设目录：`~/.config/autodl-instance/presets/`。例如 `flux2-klein-9b.yaml`：

```yaml
version: 1
name: flux2-klein-9b
description: FLUX.2 Klein 9B KV
models:
  - diffusion_models/flux-2-klein-9b-kv.safetensors
  - text_encoders/qwen_3_8b_fp8mixed.safetensors
  - vae/flux2-vae.safetensors
```

```bash
autodl models preset list
autodl models preset show flux2-klein-9b
autodl models preset copy flux2-klein-9b --dry-run
autodl models preset copy flux2-klein-9b
autodl models preset status
```

- tmp 已存在：跳过，不比对版本、不覆盖。即使 fs 没有原件也保留本地文件。
- tmp 不存在、fs 存在：复制，保持相对路径。
- 两边都不存在：报告缺失，本次不开始复制。
- 空间不足：开始前报错；中途磁盘写满则报错，已完成文件保留。
- 没有激活状态、归属数据库、切换、清理或自动删除。需要删除或更新时用户手动处理。
- `use` 仅是 `copy` 的兼容别名，含义也是复制；已移除 `reset`。
- `--dry-run` 只检查，不创建目录或文件；不要求 ComfyUI 正在运行。

复制在目标目录使用唯一的 `.part` 文件，完成后原子发布，已有目标绝不覆盖。
失败会清理本次临时文件；强制终止留下的 `.part` 可手动删除。
发现旧式正式文件旁有 `.aria2` 时会报告未完成下载，不把它视作完整模型。
拒绝路径穿越、越界源链接以及本地目标目录中的软链接，防止误写 fs 或其他目录。
只处理预设列出的路径，不扫描清理其他文件。模型是否已经加载到显存不影响复制。

## 下载

`autodl model download URL` 和 `autodl model download --preset NAME` 下载到同一个 tmp 模型目录。
下载使用目标旁的 `文件名.part` 和 `.part.aria2`，中断后可以续传，完成后发布正式文件名。
无需手动从 downloads 目录搬运。旧 downloads 目录内容不会自动删除。
交互下载只有用户明确选择“覆盖”时才替换已有文件；批量下载已有文件跳过。

## 配置与诊断

```bash
autodl config set local-models-dir /root/autodl-tmp/ComfyUI/models
autodl config set model-presets-dir /root/.config/autodl-instance/presets
autodl models preset configure
autodl models preset status
```

fs 根目录使用 `models-dir`，本地目录使用 `local-models-dir`，服务端口使用 `model-port`（默认 6006）。
也支持对应的 `AUTODL_LOCAL_MODELS_DIR`、`AUTODL_MODEL_PRESETS_DIR` 环境变量。
配置过的根目录变更需检查现有搜索配置，不自动迁移文件。
`status` 显示磁盘配置与运行中的实际顺序；服务不可验证时 `priority_ready` 为 false。
本地 HTTP 检查绕过代理。复制前检查真实挂载、容量与 inode；允许 AutoDL 的 fs 挂载别名。

旧 `.autodl-model-cache` 不再使用或自动清理。升级配置会替换已识别的旧受管配置块，保留用户配置。
旧目录中的模型需要人工整理；不能仅删除目录，因为其中可能存在唯一副本。
`init/migrate` 不再迁移模型文件或建立指向 fs 的模型类别链接，output/user 保留原行为。
自定义节点如果直接硬编码模型路径，需另外检查；标准搜索顺序不保证能覆盖这类节点。

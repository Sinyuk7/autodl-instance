# autodl-instance

AutoDL 上的 ComfyUI 环境、代理和模型管理工具。

工作流模型复制预设：`autodl models preset --help`，参见[预设与统一模型目录说明](docs/MODEL_PRESETS.md)。

## 安装

在现有源码目录执行（需要 uv）：

```bash
cd /root/autodl-instance
uv tool install --editable --force .
autodl --help
```

CLI 直接使用当前源码。修改 Python 文件后立即生效；修改依赖后重新执行安装命令。

## 使用

先确认本地数据盘和文件存储已挂载：

```bash
findmnt -T /root/autodl-tmp
findmnt -T /root/autodl-fs
mountpoint /root/autodl-tmp
mountpoint /root/autodl-fs
df -hT /root /root/autodl-tmp /root/autodl-fs
df -i /root /root/autodl-tmp /root/autodl-fs
```

```bash
autodl secrets set mihomo-subscription-url  # 使用 Mihomo 时配置；交互输入
autodl init       # 每次开机：检查挂载、创建缺失目录、建立安全链接、初始化代理
autodl status     # 只读检查
autodl setup      # 新实例首次安装：仅安装程序和依赖
autodl migrate    # 显式整理 output/user，保留冲突
autodl init       # 安装后及日后每次开机执行
autodl start      # 前台启动，默认 --highvram，监听 0.0.0.0:6006
autodl stop       # 停止确认归属的 ComfyUI 和代理进程
```

`autodl start --vram-mode normal` 使用 ComfyUI 默认显存策略，便于与默认的 high 模式对照。high 适用于模型能装入显存的工作流；当前 ComfyUI 在此模式下关闭 DynamicVRAM。比较同一工作流、种子和分辨率的首次加载、预热后耗时与显存峰值，再决定使用哪种模式。

已有配置在重复 init 时保留，显式参数可覆盖；配置未变时不重写配置文件。健康 Mihomo 会复用。ComfyUI 尚未安装时只准备存储目标，不创建源码目录。

模型固定使用 tmp 和 fs 两套目录，ComfyUI 优先 tmp、其次 fs。`init/migrate` 不迁移模型或建立指向 fs 的类别链接。预设只从 fs 复制缺失文件到 tmp，同名跳过，删除由用户手动操作。

`init` 和 `migrate` 共用 `src/lib/migration` 管理 output/user：output 根目录保持实体目录，仅迁移、链接直接子目录，根目录文件保留；双方非空时 init 跳过，migrate 显式合并并保留冲突。user 保持整目录策略。已有非空数据不自动覆盖，迁移期间应停止其他写入者。

首次安装使用最新版 comfy-cli 和 ComfyUI 最新稳定版，依赖跟随 ComfyUI 自己的 requirements.txt；项目不维护依赖版本锁定。无卡也可安装，GPU 推理需有卡后验证。

## 模型

```bash
autodl secrets set hf-token               # 需要认证时设置
autodl model download 'https://huggingface.co/组织/仓库/resolve/main/模型.safetensors'
autodl model download --preset FLUX.2-klein-9B
autodl model list
```

模型直接下载到 tmp 模型目录，使用 `.part` 续传，成功后发布正式文件并生成隐藏的 `.meta`。HuggingFace 使用文件的 resolve 地址。

## 默认路径

| 内容 | 路径 |
|------|------|
| ComfyUI 源码 | /root/ComfyUI |
| 独立 Python 环境 | /root/.venvs/comfyui |
| 模型库 | /root/autodl-fs/models |
| 输出 | /root/autodl-fs/output |
| 本地模型 | /root/autodl-tmp/ComfyUI/models |
| 缓存 | /root/autodl-tmp/ComfyUI/cache |
| 临时文件 | /root/autodl-tmp/ComfyUI/temp |
| user 工作目录 | /root/autodl-tmp/comfyui-workspace/user |
| 本机配置与代理 | ~/.config/autodl-instance/ |

本地盘在实例释放后丢失，重要工作流需另存文件存储。秘密留在系统盘，代理配置使用 600 权限。旧本机配置可能覆盖默认路径，可用 `autodl config show` 检查。

更多：[开发说明](CONTRIBUTING.md) · [实现逻辑](src/README.md) · [测试](tests/README.md)

模型下载直接保存到 `/root/autodl-tmp/ComfyUI/models/`；完成前使用 `.part` 文件。预设复制使用 `autodl models preset copy NAME`，不自动删除任何模型。

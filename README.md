# autodl-instance

AutoDL 上的 ComfyUI 环境、代理和模型管理工具。

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
autodl migrate    # 仅在已有实体目录需要搬迁时执行；保留冲突，不创建链接
autodl init       # 安装／迁移后完成链接，日后每次开机执行
autodl start      # 前台启动，监听 0.0.0.0:6006
autodl stop       # 停止确认归属的 ComfyUI 和代理进程
```

已有配置在重复 init 时保留，显式参数可覆盖；配置未变时不重写配置文件。健康 Mihomo 会复用。init 不搬迁或删除已有数据：正确链接跳过，缺失路径或空目录可建立链接，非空目录提示先执行 migrate，错误链接拒绝自动切换。ComfyUI 尚未安装时只准备存储目标，不创建源码目录。

setup 不初始化代理、不迁移数据、不建立数据链接。init 的代理环境仅作用于自身进程；安装需要代理时可使用单命令环境，例如 `HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890 NO_PROXY=127.0.0.1,localhost autodl setup`（端口以实际配置为准）。

migrate 只搬迁 ComfyUI 下实体 models/user/output 目录，保留目标已有文件；同内容源副本去重，不同内容源文件另存 `.autodl-model-conflicts` 或 `.autodl-migration-conflicts`，不会覆盖已有冲突副本。源目录保持为空，随后由 init 建立链接。错误链接不会由 migrate 自动切换。迁移发布使用 Linux 原子不覆盖操作；文件系统不支持时会报错并保留源文件。迁移期间停止对这些目录的写入；迁移不是跨目录事务，中断后可能已有部分文件搬迁，可修复原因后重试。

首次安装使用最新版 comfy-cli 和 ComfyUI 最新稳定版，依赖跟随 ComfyUI 自己的 requirements.txt；项目不维护依赖版本锁定。无卡也可安装，GPU 推理需有卡后验证。

## 模型

```bash
autodl secrets set hf-token               # 需要认证时设置
autodl model download 'https://huggingface.co/组织/仓库/resolve/main/模型.safetensors'
autodl model download --preset FLUX.2-klein-9B
autodl model list
```

模型先下载到 downloads，完成后生成隐藏的 .meta 文件。确认文件后，将模型和 .meta 一起手动移入模型库；不会自动发布或更新 model-lock.yaml。HuggingFace 使用文件的 resolve 地址。

## 默认路径

| 内容 | 路径 |
|------|------|
| ComfyUI 源码 | /root/ComfyUI |
| 独立 Python 环境 | /root/.venvs/comfyui |
| 模型库 | /root/autodl-fs/ComfyUI/models |
| 输出 | /root/autodl-fs/ComfyUI/output |
| 下载暂存 | /root/autodl-tmp/ComfyUI/downloads |
| 缓存 | /root/autodl-tmp/ComfyUI/cache |
| 临时文件 | /root/autodl-tmp/ComfyUI/temp |
| user 工作目录 | /root/autodl-tmp/comfyui-workspace/user |
| 本机配置与代理 | ~/.config/autodl-instance/ |

本地盘在实例释放后丢失，重要工作流需另存文件存储。秘密留在系统盘，代理配置使用 600 权限。旧本机配置可能覆盖默认路径，可用 `autodl config show` 检查。

更多：[开发说明](CONTRIBUTING.md) · [实现逻辑](src/README.md) · [测试](tests/README.md) · [主机交接](docs/NEXT_SESSION_PLAN.md)

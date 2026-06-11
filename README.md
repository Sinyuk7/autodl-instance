# autodl-instance

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

AutoDL 云 GPU 实例上的 ComfyUI 工作站恢复工具。运行时只支持已安装的 `autodl` CLI；源码仓库仅用于开发、测试、构建和发布。

## 快速开始

### 1. 安装 CLI

```bash
uv tool install autodl-instance
```

### 2. 配置用户数据仓库

```bash
autodl config set userdata-repo git@github.com:username/my-comfyui-backup.git
```

可选路径配置：

```bash
autodl config set userdata-dir /root/autodl-tmp/my-comfyui-backup
autodl config set workspace-dir /root/autodl-tmp/autodl-workspace
autodl config set models-dir /root/autodl-tmp/models
autodl config set comfy-dir /root/ComfyUI
```

查看当前配置：

```bash
autodl config show
autodl config path
```

### 3. 初始化和启动

```bash
autodl setup
autodl start
```

关机或释放实例前同步：

```bash
autodl bye
```

`my-comfyui-backup` 只保存用户资产：`user/`、`script_examples/`、`mihomo/`、`model-lock.yaml`、节点 snapshot，以及 `.autodl-instance/` 元数据。不要把工具源码、venv、release build 产物或 secrets 放进数据仓库。

## 常用命令

| 命令 | 功能 |
|------|------|
| `autodl setup` | 初始化 AutoDL 环境和 ComfyUI |
| `autodl start` | 启动 ComfyUI 服务 |
| `autodl bye` | 关机前同步用户数据 |
| `autodl status` | 快速检查 workspace、userdata、models 状态 |
| `autodl doctor` | 深度诊断 Git、模型、网络、磁盘、旧布局 |
| `autodl migrate detect-old-layout` | 只读检测旧源码布局数据目录 |
| `autodl model ...` | 模型下载与状态管理 |
| `source turbo` | 注入 AutoDL 网络加速环境变量 |

## Secrets

敏感信息只写入本机 secret file，不写入数据仓库：

```bash
autodl secrets set hf-token
autodl secrets set civitai-token
autodl secrets set mihomo-subscription-url
autodl secrets list
```

删除 secret：

```bash
autodl secrets unset hf-token
```

环境变量仍是最高优先级：`HF_TOKEN`、`CIVITAI_API_TOKEN`。

## 模型管理

交互式下载：

```bash
autodl model download https://civitai.com/models/12345
autodl model download https://huggingface.co/xxx/xxx/xxx.safetensors
```

按内置预设下载：

```bash
autodl model download -p FLUX.2-klein-9B
```

查看状态：

```bash
autodl model types
autodl model list
autodl model status
autodl model cache
autodl model cache clear
```

`model-lock.yaml` 是“曾经有什么 + 指纹 + 来源”的清单，不是自动下载任务表。工具不会在 `setup` / `start` / `bye` 中自动下载模型；缺失模型会在 `model status` 中提示，由用户手动执行下载。

## 旧布局迁移

如果旧实例曾把用户数据放在源码 checkout 下，先运行：

```bash
autodl migrate detect-old-layout
autodl doctor
```

工具只提示旧目录和当前写入目录，不会自动移动或删除任何数据。确认迁移完成后再手动清理旧目录。

## 开发者

源码仓库仅用于开发、测试、构建和发布。开发说明见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

[MIT License](LICENSE)

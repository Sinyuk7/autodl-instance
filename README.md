# autodl-instance

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

AutoDL 云 GPU 实例上的 ComfyUI 工作环境管理器，负责本地初始化、网络代理、模型下载、节点安装和 ComfyUI 启停，不提供远程备份或跨实例同步。

## 快速开始

### 1. 安装 CLI

```bash
uv tool install autodl-instance
```

### 2. 配置本地工作区

可选路径配置：

```bash
autodl config set workspace-data-dir /root/autodl-tmp/comfyui-workspace
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

停止服务：

```bash
autodl stop
```

工作数据保存在数据盘的本地 workspace 中，不会被 Git 提交或上传到远程仓库。

## 常用命令

| 命令 | 功能 |
|------|------|
| `autodl setup` | 初始化 AutoDL 环境和 ComfyUI |
| `autodl start` | 启动 ComfyUI 服务 |
| `autodl stop` | 停止 ComfyUI 和代理 |
| `autodl status` | 快速检查 workspace、ComfyUI、models 状态 |
| `autodl doctor` | 深度诊断 Git、模型、网络、磁盘、旧布局 |
| `autodl model ...` | 模型下载与状态管理 |
| `source turbo` | 注入 AutoDL 网络加速环境变量 |

## Secrets

敏感信息只写入本机 secret file，不写入工作区：

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

`model-lock.yaml` 是本地模型状态清单，不是自动下载任务表。工具不会在 `setup` / `start` / `stop` 中自动下载模型；缺失模型会在 `model status` 中提示。

## 开发者

源码仓库仅用于开发、测试、构建和发布。开发说明见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

[MIT License](LICENSE)

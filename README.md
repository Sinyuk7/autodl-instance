# autodl-instance

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

AutoDL 云 GPU 实例上的 ComfyUI 工作环境管理器。它负责准备网络环境、安装 PyTorch 和 ComfyUI、安装默认自定义节点、持久化工作数据，以及管理模型下载。

> 当前项目尚未发布到 PyPI，也没有 GitHub Release。请按下方命令直接从 GitHub 安装。项目不提供远程备份或跨实例同步；数据安全仍依赖 AutoDL 数据盘和你自己的备份策略。

## 在 AutoDL 上使用

### 运行前确认

- AutoDL Linux GPU 实例，使用 `root` 用户运行。
- Python 3.10 或更高版本。
- 当前 Torch 配置要求 NVIDIA 驱动主版本不低于 `580`，可先执行 `nvidia-smi` 检查。
- `/root/autodl-tmp` 是持久化数据盘，并且有足够空间存放模型和输出。

### 1. 安装 uv 和 autodl-instance

普通使用不需要先 `git clone`。安装器会直接从 GitHub 构建并安装 `autodl` 命令：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv tool install "git+https://github.com/Sinyuk7/autodl-instance.git@main"
autodl --help
```

如果终端仍提示 `autodl: command not found`，重新登录终端，或执行：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### 2. 初始化目录配置

默认目录已经按 AutoDL 的系统盘和数据盘分好，直接初始化即可：

```bash
autodl init
autodl config show
```

默认布局：

| 内容 | 默认路径 | 说明 |
|------|----------|------|
| 工具配置与 secrets | `/root/.config/autodl-instance/` | 系统盘；新实例需要重新配置 |
| 运行状态、日志和辅助命令 | `/root/autodl-tmp/autodl-workspace/` | 数据盘 |
| ComfyUI 的 `user`、`output` | `/root/autodl-tmp/comfyui-workspace/` | 数据盘，通过软链接接入 ComfyUI |
| 模型 | `/root/autodl-tmp/models/` | 数据盘，通过软链接接入 ComfyUI |
| ComfyUI 程序 | `/root/ComfyUI/` | 系统盘，可由 `setup` 重建 |

只有需要改变默认布局时才使用 `autodl config set`，例如：

```bash
autodl config set models-dir /root/autodl-tmp/models
autodl config set comfy-dir /root/ComfyUI
```

### 3. 配置可选凭据

只使用公开模型时可以跳过。命令会交互式读取值，不会把 token 回显到终端：

```bash
autodl secrets set hf-token
autodl secrets set civitai-token
```

需要使用自己的 Mihomo/Clash 订阅时再配置：

```bash
autodl secrets set mihomo-subscription-url
```

未配置 Mihomo 时，工具会优先尝试 AutoDL 自带的学术加速；两者都不可用时使用直连。

### 4. 装配环境

```bash
autodl setup
```

首次执行会安装必要系统工具、检查驱动、安装锁定的 `torch 2.11.0+cu130`、`torchvision 0.26.0+cu130`、`torchaudio 2.11.0+cu130`，部署 ComfyUI `0.36.0`，建立数据盘软链接，并安装内置节点。这个过程会下载较大的依赖；重复执行会复用已有状态。

安装完成后检查：

```bash
autodl status
autodl doctor
```

### 5. 启动和停止 ComfyUI

```bash
autodl start
```

ComfyUI 监听 `0.0.0.0:6006`。在 AutoDL 控制台中打开实例的 6006 端口访问。`start` 默认以前台方式运行，按 `Ctrl+C` 可结束当前进程；也可以在另一个终端执行：

```bash
autodl stop
```

停止时会尝试保存一份 ComfyUI-Manager 节点快照到数据盘。

## 模型管理

`setup` 不会自动下载模型。可以按 URL 或内置预设下载：

```bash
autodl model download https://civitai.com/models/12345
autodl model download https://huggingface.co/owner/repo/resolve/main/model.safetensors
autodl model download -p FLUX.2-klein-9B
```

查看模型类型、本地文件和锁定状态：

```bash
autodl model types
autodl model list
autodl model status
autodl model cache
```

`model-lock.yaml` 是本地模型状态清单，不是自动下载任务表。缺失或发生变化的模型只会在 `autodl model status` 中提示。

## 手动升级 ComfyUI

自动装配固定使用经过验证的 ComfyUI `0.36.0`。用户可以在当前实例上主动升级到最新稳定版：

```bash
autodl stop
comfy --workspace /root/ComfyUI update comfy --version latest
autodl start
```

`comfy update` 会更新 ComfyUI 及其 Python 依赖，但不会更新 Torch。升级后再次执行普通 `autodl setup` 不会自动降级 ComfyUI。需要回到项目验证版本时执行：

```bash
comfy --workspace /root/ComfyUI update comfy --version 0.36.0
```

手动升级属于用户选择的本机状态；升级自定义节点前建议保留工作流和节点快照。

## 新实例恢复

本项目不会把数据同步到 Git。换一台 AutoDL 实例时：

1. 确认原数据盘仍挂载在 `/root/autodl-tmp`，或先自行恢复数据盘备份。
2. 重新安装 `uv` 和 `autodl-instance`。
3. 重新执行 `autodl init`，并重新录入本机 secrets。
4. 执行 `autodl setup` 重建系统盘上的 ComfyUI，并重新连接已有数据。
5. 执行 `autodl doctor` 检查目录、模型和网络状态。

`/root/autodl-tmp` 中的数据不是远程备份。释放数据盘或删除其中内容后，本工具无法恢复。

## 是否需要 clone 仓库

普通使用不需要 clone。只有要修改代码、运行测试或参与开发时，才建议把源码 clone 到数据盘，避免工作副本随系统盘重建而丢失：

```bash
cd /root/autodl-tmp
git clone <repository-url> autodl-instance
cd autodl-instance
uv tool install --editable .
autodl --help
```

开发和测试说明见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 常用命令

| 命令 | 功能 |
|------|------|
| `autodl init` | 写入默认或指定的本机路径配置 |
| `autodl config show` | 查看本机配置 |
| `autodl setup` | 初始化网络、PyTorch、ComfyUI、工作区和节点 |
| `autodl start` | 在 6006 端口前台启动 ComfyUI |
| `autodl stop` | 停止 ComfyUI 和代理，并尝试保存节点快照 |
| `autodl status` | 快速检查工作区、ComfyUI 和模型状态 |
| `autodl doctor` | 深度检查配置、网络、磁盘和缓存 |
| `autodl model ...` | 下载和检查模型 |
| `source turbo` | 把当前网络配置注入当前 shell |

更新 GitHub 版本：

```bash
uv tool install --force "git+https://github.com/Sinyuk7/autodl-instance.git@main"
```

## License

[MIT License](LICENSE)

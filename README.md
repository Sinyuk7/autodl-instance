# autodl-instance

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> 🚀 AutoDL 云 GPU 实例环境配置工具

专为 [AutoDL](https://www.autodl.com/) 云 GPU 实例设计，实现 **Infrastructure as Code + User Data Roaming**（基础设施即代码 + 用户数据漫游）。

## ✨ 特性

- **快速部署** - 通过少量命令完成 ComfyUI 环境配置
- **缓存管理** - 自动将缓存重定向至数据盘，节省系统盘空间
- **开箱即用** - 首次运行自动安装所需依赖
- **无卡初始化** - 支持在无 GPU 模式下完成环境初始化
- **模型管理** - 支持交互式下载，识别 HuggingFace/CivitAI 链接
- **数据漫游** - 工作流、节点快照、模型记录自动同步到私有仓库，跨实例无缝迁移

## 📦 快速开始

### 1. 克隆项目到 AutoDL 数据盘

```bash
cd /root/autodl-tmp
git clone https://github.com/Sinyuk7/autodl-instance.git
cd autodl-instance
```

### 2. 配置用户信息（可选但推荐）

```bash
cp env.yaml.example env.yaml
vim env.yaml
```

配置内容包括 Git 用户名/邮箱、SSH 密钥（用于免密推送）、HuggingFace 和 CivitAI 的 API Token。

### 3. 一键初始化环境

```bash
chmod +x init.sh
./init.sh
```

这将自动完成：
- ✅ 安装 `uv` 极速包管理器
- ✅ 安装 `comfy-cli` 官方 CLI 工具
- ✅ 将 `.cache` 目录迁移至数据盘（避免系统盘爆满）
- ✅ 配置 Git/SSH 环境
- ✅ 部署 ComfyUI + ComfyUI-Manager
- ✅ 安装预设的自定义节点
- ✅ 同步用户配置和工作流

> 💡 **省钱技巧**：可以在「无卡模式」下完成初始化，下载完成后关机，再以有卡模式启动服务。

### 4. 启动 ComfyUI 服务

```bash
start
```

### 5. 关机前同步

```bash
bye
```

自动保存自定义节点快照、模型下载记录、工作流文件以及用户配置，确保下次开机能完整还原工作环境。

---

### 快捷命令

`./init.sh` 完成后，以下全局命令可直接在终端使用：

| 命令 | 功能 |
|------|------|
| `start` | 启动 ComfyUI 服务 (附加 `--debug` 可开启调试模式) |
| `bye` | 关机前同步 |
| `model` | 模型下载管理 |
| `turbo` | 启用 AutoDL 学术加速（加速 GitHub/HuggingFace） |

## ⚙️ 配置说明

### 用户配置 (`env.yaml`)

```yaml
# Git 配置（用于免密推送）
git:
  user_name: "YourName"
  user_email: "your.email@example.com"
  ssh_private_key: ""   # Base64 编码的私钥（可选）
  ssh_public_key: ""    # 公钥内容（可选）

# 数据同步配置（可选 - 启用数据漫游）
sync:
  # 私有数据仓库，用于备份工作流、模型记录、节点配置
  # 若不配置，数据仅保存在本地
  userdata_repo: "git@github.com:username/my-comfyui-backup.git"

# API Keys
api_keys:
  hf_api_token: "hf_xxxxxxxxxxxx"        # HuggingFace Token
  civitai_api_token: "xxxxxxxxxxxxxxxx"  # CivitAI API Token
```

### 数据漫游（跨实例同步）

配置 `sync.userdata_repo` 后，你的用户数据将自动同步到私有 Git 仓库：

| 数据类型 | 说明 |
|---------|------|
| 工作流 | ComfyUI 保存的 `.json` 工作流文件 |
| 节点快照 | ComfyUI-Manager 生成的节点状态快照 |
| 模型记录 | 已下载模型的清单（`model_lock.yaml`） |
| 用户配置 | ComfyUI 设置、节点偏好等 |

**工作流程：**
- `init` 时自动从私有仓库拉取最新数据
- `bye` 时自动将变更推送到私有仓库
- 新开实例时，配置相同的 `userdata_repo` 即可无缝恢复

> 如果不配置私有仓库，数据会保存在本地 `my-comfyui-backup` 目录，不影响正常使用。

### 网络与镜像配置

默认 `setup` 时会自动启用 AutoDL 学术加速，加速 GitHub / HuggingFace 等资源。

如果学术加速不稳定，可在 `src/addons/system/manifest.yaml` 中配置镜像：

```yaml
mirrors:
  pypi: "https://mirrors.aliyun.com/pypi/simple/"
  huggingface: "https://hf-mirror.com"
```

## 📥 模型下载

`setup` 完成后，可直接使用全局 `model` 命令管理模型。

### 交互式下载

```bash
model download https://civitai.com/models/12345
model download https://huggingface.co/xxx/xxx/xxx.safetensors
```

自动识别来源，引导你确认文件名、选择模型类型和子目录。

### 按预设批量下载

预设定义在 `src/addons/models/manifest.yaml`，一键下载完整工作流所需的全部模型：

```bash
model download -p FLUX.2-klein-9B
```

`manifest.yaml` 语法示例：
```yaml
FLUX.2-klein-9B:
  - url: "https://huggingface.co/xxx/xxx.safetensors"
    type: "checkpoints"
  - url: "https://civitai.com/models/12345"
    type: "loras"
    name: "my_lora.safetensors"
```

已下载的模型自动跳过，不会重复下载。

### 管理模型

```bash
model types          # 查看可用的模型类型
model list           # 列出已下载的模型
model status         # 查看 lock 文件记录
model remove <name>  # 删除模型
model cache          # 查看下载缓存大小
model cache clear    # 清理全部下载缓存
```

### 下载策略

| URL 来源 | 下载工具 | 特点 |
|---------|---------|------|
| HuggingFace | `huggingface_hub` + `hf_xet` | 官方 Hub API，版本感知缓存，xet 分块去重加速 |
| CivitAI | `aria2c` 多线程 | 自动解析模型信息，支持 API Token |
| 直链 | `aria2c` 多线程 | 32 线程并发，断点续传 |

## 🔧 常见问题

### 1. 安装卡住无响应

**原因**：之前中断的进程（Ctrl+Z / Ctrl+C）持有 uv 锁文件。

**解决**：
```bash
pkill -9 -f "python.*src.main"
rm -f /tmp/uv-*.lock
./init.sh
```

### 2. PyTorch 下载速度慢

正常现象。PyTorch 体积较大且官方源在国外，耐心等待即可。下载完成后会缓存到数据盘，下次开机无需重新下载。

### 3. SSH 密钥需要手动添加到 GitHub

**现象**：提示 `[ACTION REQUIRED] 请将以下公钥添加到 GitHub 账户`

**解决**：复制提示中的公钥，访问 https://github.com/settings/keys 添加。

> 更好的方式：在 `env.yaml` 中配置本地已有的 SSH 密钥，避免每次新建实例都要重新添加。

### 4. ModuleNotFoundError: No module named 'src'

必须以模块方式运行：

```bash
python -m src.main setup  # ✅ 正确
python src/main.py setup  # ❌ 错误
```

## 👨‍💻 开发者

如果你想了解项目架构或参与开发，请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 License

[MIT License](LICENSE)

---

**Made with ❤️ for AutoDL users**
# autodl-instance

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> 🚀 AutoDL 云 GPU 实例环境配置工具

专为 [AutoDL](https://www.autodl.com/) 云 GPU 实例设计，实现 **Infrastructure as Code + User Data Roaming**（基础设施即代码 + 用户数据漫游）。

## ✨ 特性

- **快速部署** - 通过少量命令完成 ComfyUI 环境配置
- **状态诊断** - 提供 `status` / `doctor` 检查模型、Git、快照、网络和磁盘状态
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

### 2. 一键初始化环境

```bash
chmod +x init.sh
./init.sh
```

这将自动完成：
- ✅ 安装 `uv` 极速包管理器
- ✅ 安装 `comfy-cli` 官方 CLI 工具
- ✅ 配置 Git/SSH 环境
- ✅ 部署 ComfyUI + ComfyUI-Manager
- ✅ 安装预设的自定义节点
- ✅ 同步用户配置和工作流

> 💡 **省钱技巧**：可以在「无卡模式」下完成初始化，下载完成后关机，再以有卡模式启动服务。

### 3. 启动 ComfyUI 服务

```bash
start
```

### 4. 关机前同步

```bash
bye
```

自动保存自定义节点快照、模型清单、工作流文件以及用户配置。`bye` 会在 Git 推送或模型清单生成失败时返回非 0；此时不要释放实例，先按错误提示处理。

---

## ⌨️ 快捷命令

`./init.sh` 完成后，以下全局命令可直接在终端使用：

| 命令 | 功能 |
|------|------|
| `start` | 启动 ComfyUI 服务 (附加 `--debug` 可开启调试模式) |
| `bye` | 关机前同步 |
| `model` | 模型下载管理 |
| `status` | 快速检查工作区恢复状态 |
| `doctor` | 深度诊断 Git、模型、网络、磁盘与缓存 |
| `turbo` | 启用 AutoDL 学术加速（加速 GitHub/HuggingFace） |

## ⚙️ 可选配置

所有配置均为**可选**，未配置的功能会自动跳过。配置文件分散在各模块目录下：

### Git 免密推送

```bash
cd src/addons/git_config
cp manifest.yaml.example manifest.yaml
vim manifest.yaml
```

配置 `user_name`、`user_email`、SSH 密钥后，可启用私有仓库的免密推送。

### API Token（模型下载加速）

```bash
cd src/lib/download
cp secrets.yaml.example secrets.yaml
vim secrets.yaml
```

配置 HuggingFace / CivitAI 的 API Token，解锁需要登录的模型下载。

### 数据漫游（跨实例同步）

编辑 `src/addons/userdata/manifest.yaml`，配置 `userdata_repo` 为你的私有 Git 仓库地址：

```yaml
userdata_repo: "git@github.com:username/my-comfyui-backup.git"
```

配置后，你的用户数据将自动同步：

| 数据类型 | 说明 |
|---------|------|
| 工作流 | ComfyUI 保存的 `.json` 工作流文件 |
| 节点快照 | ComfyUI-Manager 生成的节点状态快照 |
| 模型记录 | 已下载模型的清单与来源，不包含模型本体 |
| 用户配置 | ComfyUI 设置、节点偏好等 |

> 如果不配置私有仓库，数据会保存在本地 `my-comfyui-backup` 目录，不影响正常使用。

## 📥 模型下载

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

已下载的模型自动跳过，不会重复下载。下载前会做只读磁盘预检：能拿到远端大小时，空间不足会直接失败并提示下一步；远端大小未知时只 warning，仍继续交给 `aria2c` 下载。

### 管理模型

```bash
model types          # 查看可用的模型类型
model list           # 列出已下载的模型
model status         # 查看 lock 文件记录
model remove <name>  # 删除模型
model cache          # 查看下载缓存大小
model cache clear    # 清理全部下载缓存
```

`model-lock.yaml` 是“曾经有什么 + 指纹 + 来源”的清单，不是下载任务表。工具不会在 `setup` / `start` / `bye` 中自动下载模型；缺失模型会在 `model status` 中提示，由用户手动执行下载。

### 下载策略

| URL 来源 | 下载工具 | 特点 |
|---------|---------|------|
| HuggingFace | `aria2c` 多线程 | 支持 HF mirror / HF_TOKEN，断点续传 |
| CivitAI | `aria2c` 多线程 | 自动解析模型信息，支持 API Token |
| 直链 | `aria2c` 多线程 | 多线程并发，断点续传 |

> `.cache` 不会被默认整体迁移。可通过 `doctor` 查看 HuggingFace / Torch / uv 等 cache 目录大小，再决定是否手动清理或迁移。

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

> 更好的方式：在 `src/addons/git_config/manifest.yaml` 中配置本地已有的 SSH 密钥，避免每次新建实例都要重新添加。

## 👨‍💻 开发者

如果你想了解项目架构或参与开发，请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 License

[MIT License](LICENSE)

---

**Made with ❤️ for AutoDL users**

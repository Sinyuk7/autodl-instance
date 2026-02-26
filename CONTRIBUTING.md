# 贡献指南 (CONTRIBUTING)

本项目专为 **AutoDL** 平台设计，开发前请了解目标环境特性：

## 🎯 AutoDL 环境摘要

1. **系统与权限**: Ubuntu (18.04/20.04+)，默认 `root` 登录，拥有最高权限。
2. **Python 环境**: 预装 Miniconda，默认 Python 3.x (通常 3.11)。支持 `conda` 切换环境。
3. **驱动与框架**: 预装 NVIDIA Driver、CUDA Toolkit 及 PyTorch/TF 等框架。**无需**在脚本中重新安装底层驱动。
4. **存储结构**: 
   - 系统盘 (`/root`): 容量小，重置会清空。
   - 数据盘 (`/root/autodl-tmp`): 容量大。**高频缓存和项目工作区必须放在数据盘**。
5. **网络与工具**: 支持 SSH/JupyterLab。内置"学术加速"，由 `src/lib/network.py` 统一管理（代理、HF 镜像、API Token），所有 Python 入口通过 `setup_network()` 初始化，用户终端可通过 `eval $(turbo)` 注入。
6. **开放端口**: 由于实例无独立公网IP，因此不能开放任意端口。但是 AutoDL 为每个实例的 6006 和 6008 端口都映射了一个可公网访问的地址，也就是将实例中的 6006 和 6008 端口映射到公网可供访问的 ip:port 上，映射的协议支持 TCP 或 HTTP，协议可自行选择，ip:port 可在「自定义服务」入口获取。

---

## 🛠️ 核心开发规范

1. **强类型 Context**: 使用 `dataclasses` 替代 `Dict` 传递全局状态。
2. **友好错误提示**: 封装统一的命令执行函数 (`src.core.utils.run_command`)，拦截 Python 堆栈，输出小白友好的中文提示。
3. **结构化日志**: 引入日志文件记录 (`src.core.utils.logger`)，便于排查断网或清屏后的问题。终端输出 INFO 级别，文件输出 DEBUG 级别。
4. **状态持久化**: 使用统一的 `StateManager` (`src.core.utils.StateManager`) 记录长耗时任务的安装进度，防止"半安装"状态。
5. **进程与端口清理**: 
   - 处理 `Ctrl+Z` 挂起残留：使用 `kill_process_by_name` 清理僵尸进程。
   - 处理 `Ctrl+C` 异常退出：服务启动前使用 `release_port` 释放端口，避免 "address already in use" 错误。

---

## 📄 配置文件规范

### 架构概述：去中心化 Manifest

本项目采用 **去中心化配置** 架构——每个插件 (addon) 和库 (lib) 模块在自己的目录下维护
`manifest.yaml`（公开技术参数）和可选的 `secrets.yaml`（敏感凭证）。

启动时 `main.py` 的 `load_manifests()` 函数会扫描 `src/addons/*/manifest.yaml` 和
`src/lib/*/manifest.yaml`，将所有 manifest 预加载到 `AppContext.addon_manifests` 字典中。
插件通过 `self.get_manifest(ctx)` 获取自己的配置，无需直接读文件。

### 现有配置文件一览

| 文件 | 用途 | 备注 |
|------|------|------|
| `src/addons/torch_engine/manifest.yaml` | PyTorch 版本、CUDA 包、下载源 | |
| `src/addons/system/manifest.yaml` | 系统工具列表、PyPI/HF 镜像 | |
| `src/addons/git_config/manifest.yaml` | Git 用户名、邮箱、SSH 私钥 | **已 gitignore**，提供 `.example` |
| `src/addons/nodes/manifest.yaml` | ComfyUI 自定义节点列表 | |
| `src/addons/userdata/manifest.yaml` | 需要软链接持久化的目录列表 | |
| `src/addons/models/manifest.yaml` | 模型预设（一键部署工作流所需模型） | Schema: `src/addons/models/schema.py` → `PresetsFile` |
| `src/addons/models/extra_model_paths.yaml` | ComfyUI 模型路径映射模板 | 由程序渲染后写入 ComfyUI |
| `src/lib/download/manifest.yaml` | aria2 / hf_hub 下载参数 | |
| `src/lib/download/secrets.yaml` | HF Token、CivitAI Token 等 | **已 gitignore**，提供 `.example` |

### 新增配置文件的规范

**每个模块自治管理配置，遵循以下约定：**

1. **公开技术参数** → 放在模块目录下的 `manifest.yaml`
   - 启动时由 `load_manifests()` 统一扫描加载
   - 插件通过 `self.get_manifest(ctx)` 读取

2. **敏感凭证** → 放在模块目录下的 `secrets.yaml`
   - 必须在 `.gitignore` 中排除
   - 提供 `secrets.yaml.example` 作为开发者模板
   - 由需要该凭证的代码自行加载（如 `src/lib/network.py`）

3. **Schema 验证**（推荐但非强制）：
   - 结构复杂的 manifest 建议在同目录的 `schema.py` 中定义 Pydantic Model
   - 结构极简（如仅一个字符串列表）、机器生成的 lockfile、或第三方工具模板文件可不加 Schema
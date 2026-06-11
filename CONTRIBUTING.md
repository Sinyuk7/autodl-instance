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

### 运行时配置

用户运行时只通过 `autodl` CLI 管理配置：

- 非敏感配置写入 `~/.config/autodl-instance/config.yaml`
- 敏感配置写入 `~/.config/autodl-instance/secrets.yaml`
- 数据仓库不保存 secrets
- 环境变量优先级高于本机配置

常用命令：

```bash
autodl config set userdata-repo git@github.com:user/my-comfyui-backup.git
autodl config set git-user-name "Your Name"
autodl secrets set hf-token
```

### Package 默认配置

插件和 lib 模块仍可维护 package 内置 `manifest.yaml`，用于公开技术默认值，例如 PyTorch 版本、节点列表、模型预设、aria2 参数和 proxy 端口。

约定：

1. package manifest 只放公开默认值，不作为用户运行期配置入口。
2. 用户覆盖项优先走 `autodl config` 或环境变量。
3. 敏感凭证优先走 `autodl secrets` 或环境变量。
4. 结构复杂的 manifest 建议在同目录的 `schema.py` 中定义 Pydantic Model。

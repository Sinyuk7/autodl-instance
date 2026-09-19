# 贡献指南 (CONTRIBUTING)

本项目专为 **AutoDL** 平台设计，开发前请了解目标环境特性：

## 🎯 AutoDL 环境摘要

1. **系统与权限**: Ubuntu (18.04/20.04+)，默认 `root` 登录，拥有最高权限。
2. **Python 环境**: 预装 Miniconda，默认 Python 3.x (通常 3.11)。支持 `conda` 切换环境。
3. **驱动与框架**: 预装 NVIDIA Driver、CUDA Toolkit 及 PyTorch/TF 等框架。**无需**在脚本中重新安装底层驱动。
4. **存储结构**: 
   - 系统盘 (`/root`): 默认 30GB。源码、ComfyUI、Python 环境、代理和主机配置放在这里并控制体积，使环境可以保存为个人镜像。
   - 本地数据盘 (`/root/autodl-tmp`): 默认 50GB、IO 高但无冗余，也不会进入系统镜像。用于当前工作集、缓存、输出和选择性的活跃模型；写入前必须确认它是真实挂载点。
   - 文件存储 (`/root/autodl-fs`): 跨同地区实例共享、多副本且不受实例释放影响。用于重要数据、代码备份、工作流和完整模型库；高 IO 数据可按需暂存到本地数据盘。
   - 镜像: AutoDL 只能在实例关机后通过控制台保存整个系统盘，不支持导入外部自定义镜像。更换镜像清空系统盘但不影响本地数据盘；共享镜像前必须移除所有机器秘密。
5. **网络与工具**: 支持 SSH/JupyterLab。网络模块管理 AutoDL 学术加速、Mihomo、镜像和 Token。只读入口不得隐式调用 `setup_network()`；不要把 `eval "$(autodl turbo)"` 当作启动代理的必要步骤，优先使用独立代理进程和命令级环境变量。
6. **开放端口**: 由于实例无独立公网IP，因此不能开放任意端口。但是 AutoDL 为每个实例的 6006 和 6008 端口都映射了一个可公网访问的地址，也就是将实例中的 6006 和 6008 端口映射到公网可供访问的 ip:port 上，映射的协议支持 TCP 或 HTTP，协议可自行选择，ip:port 可在「自定义服务」入口获取。

---

## 🛠️ 核心开发规范

1. **强类型 Context**: 使用 `dataclasses` 替代 `Dict` 传递全局状态。
2. **友好错误提示**: 封装统一的命令执行函数 (`src.core.utils.run_command`)，拦截 Python 堆栈，输出小白友好的中文提示。
3. **结构化日志**: 引入日志文件记录 (`src.core.utils.logger`)，便于排查断网或清屏后的问题。终端输出 INFO 级别，文件输出 DEBUG 级别。
4. **状态持久化**: 使用统一的 `StateManager` (`src.core.utils.StateManager`) 记录长耗时任务的安装进度，防止"半安装"状态。
5. **进程与端口清理**:
   - 必须通过 PID 文件、命令行和工作目录确认进程归属。
   - 优先发送 `SIGTERM` 并等待退出；不得为了释放 6006 杀死未知进程。

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

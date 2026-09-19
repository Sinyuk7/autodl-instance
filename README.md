# autodl-instance

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

面向 AutoDL + ComfyUI 的运维工具集和现场知识库。

这个仓库不再被视为一个可以无条件接管整台实例的“一键安装器”。它保存可审查、可重复执行的诊断和修复工具，Codex CLI 则运行在目标 AutoDL 实例上，先观察真实环境，再维护这些工具。真实主机状态始终优先于文档中的默认假设。

## 当前工作方式

1. 将源码 clone 到 AutoDL 系统盘 `/root/autodl-instance`。
2. 在主机上安装 Codex CLI，让它检查磁盘、GPU、Python、ComfyUI、Mihomo、端口和现有文件。
3. 根据现场报告，分批修改并验证本仓库的诊断或修复逻辑。
4. 模型、输出和用户数据留在数据盘；代码和可重建环境留在系统盘。

第一轮不要直接运行完整 `setup`。先使用 [Codex AutoDL 首次现场检查](docs/CODEX_AUTODL_FIRST_TASK.md)，建立经过验证的环境基线，再决定要运行或修复哪些工具。

## 项目边界

仓库当前包含以下能力：

- `autodl status` / `autodl doctor`：只读状态与环境诊断。
- 网络工具：AutoDL 学术加速、Mihomo 进程与配置管理。
- ComfyUI 生命周期工具：安装、启动、停止及数据目录连接。
- PyTorch、节点和模型相关的安装或下载任务。
- 面向真实 AutoDL 实例的测试、故障复现和运维文档。

这些能力可以独立演进。现场排障不应被迫先运行整条安装流水线；任何安装或修复动作都应来自已确认的检查结果。

## AutoDL 存储约定

| 内容 | 默认路径 | 策略 |
|------|----------|------|
| 本仓库源码 | `/root/autodl-instance/` | 系统盘；便于 Codex 修改和 Git 管理，可重新 clone |
| Codex 配置 | `/root/.codex/` | 系统盘；重置系统后需恢复 |
| 工具配置与 secrets | `/root/.config/autodl-instance/` | 系统盘；不得提交到 Git |
| ComfyUI 程序与虚拟环境 | `/root/ComfyUI/` | 系统盘；应可重建 |
| 运行状态和日志 | `/root/autodl-tmp/autodl-workspace/` | 数据盘 |
| ComfyUI `user`、`output` | `/root/autodl-tmp/comfyui-workspace/` | 数据盘，通过软链接接入 |
| 模型与大型缓存 | `/root/autodl-tmp/models/` 等 | 数据盘 |
| 压缩备份 | `/root/autodl-fs/` | 文件存储；不用于高频运行负载 |

`/root/autodl-tmp` 只有在确认它确实是已挂载的数据盘后才能写入大型文件。系统重置会清空系统盘，但不会清空已挂载的数据盘；实例释放会清除实例数据。数据盘没有冗余可靠性保证，重要数据仍需另行备份。

## 在 AutoDL 上准备工作副本

```bash
cd /root
git clone https://github.com/Sinyuk7/autodl-instance.git
cd /root/autodl-instance
git status --short
```

安装 Codex CLI 时使用 OpenAI 官方安装器。若 Mihomo 已在 `127.0.0.1:7890` 提供服务，可只为该命令设置代理，不修改系统全局代理：

```bash
env HTTP_PROXY=http://127.0.0.1:7890 \
    HTTPS_PROXY=http://127.0.0.1:7890 \
    NO_PROXY=127.0.0.1,localhost \
    sh -c 'curl -fsSL https://chatgpt.com/codex/install.sh | sh'
```

运行 Codex 时也可以采用同样的进程级代理。不要使用 `eval "$(autodl turbo)"` 作为启动 Mihomo 的必要步骤；该命令的用途是向当前 shell 导出网络变量，而不是单纯启动代理。

## 现场诊断原则

- 先读后写：先收集事实并报告，再进行安装、迁移或修复。
- 不把配置文件存在等同于服务可用；必须检查进程、监听端口和真实请求。
- 不把 `/root/autodl-tmp` 目录存在等同于数据盘已挂载。
- 不通过 `fuser -k -9 6006/tcp` 杀死未知进程；只管理能够确认归属的服务 PID。
- 不输出或提交 Mihomo 节点、订阅 URL、API token、SSH 私钥和 secrets。
- 本地 `6006` 可用而公网为 AutoDL 通用 404 时，应分别记录 ComfyUI 监听状态与平台端口映射状态。

## CLI 状态

统一入口为 `autodl`：

```bash
autodl --help
autodl status
autodl doctor
autodl setup
autodl start
autodl stop
autodl model --help
```

当前源码仍处于整理期，不能假定所有命令均可运行。已知 `src/main.py` 引用了缺失的 `src/addons/torch_engine/plugin.py`，会阻塞部分命令与测试收集。第一次现场审计应记录该问题，但不应顺手扩展成全项目重构。

## 开发顺序

当前建议顺序是：

1. 真实 AutoDL 环境与目录审计。
2. 根据审计结果修正文档、默认路径和只读诊断。
3. 恢复基本测试收集与最小可运行入口。
4. 分项修复安装、网络、进程和数据安全问题。
5. 对极端故障、幂等性、恢复路径和 destructive behavior 做专项 review。

开发约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。历史设计和 review 材料位于 `docs/archive/`，它们不是当前行为的权威来源。

## License

[MIT License](LICENSE)

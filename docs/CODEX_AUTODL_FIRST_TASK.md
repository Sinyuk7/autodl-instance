# Codex CLI：AutoDL 首次现场检查

这份任务用于 Codex CLI 第一次进入真实 AutoDL 实例。目标是建立可信的环境基线，不是立即运行一键安装，也不是在没有证据时重构项目。

主机级规则以用户提供的说明和 [项目规则](../AGENTS.md) 为准。

## 使用方式

确认 Mihomo 可用、仓库已经 clone 到 `/root/autodl-instance`、Codex CLI 已完成登录后：

```bash
cd /root/autodl-instance
codex
```

如果 Codex 自身需要代理，用进程级环境变量启动，并保留本地地址直连：

```bash
cd /root/autodl-instance
env HTTP_PROXY=http://127.0.0.1:7890 \
    HTTPS_PROXY=http://127.0.0.1:7890 \
    NO_PROXY=127.0.0.1,localhost \
    codex
```

然后粘贴下面的完整任务。

## 第一份任务提示词

```text
你现在位于一台真实的 AutoDL GPU 实例，请先接管并审计这台主机上的 ComfyUI 环境。当前阶段只做只读检查和报告：不要安装或升级软件，不要启动、停止或杀死任何进程，不要修改项目代码和配置，不要移动或删除文件，不要 commit/push。遇到需要写入或破坏性操作时先停下并说明。

工作目录应为 /root/autodl-instance。这是系统盘上的源码工作副本，后续会由你协助维护为 AutoDL + ComfyUI 运维工具集。请先读取仓库根目录及相关子目录的 AGENTS.md、README.md 和现有实现，但不要假定文档一定正确，以主机实测为准。

稳定背景：
- /root 是默认 30GB 的系统盘。源码、ComfyUI、Python 环境、Codex、代理程序和个人配置放这里并保存为私人镜像；模型、输出和大型缓存不应挤占系统盘。默认不分享镜像。
- AutoDL 不能导入外部自定义镜像。保存整个系统盘需要用户先关机，再在控制台执行；加载或更换镜像会清空系统盘但不影响本地数据盘。镜像可以共享，但共享前必须清理订阅、Token、SSH 私钥等秘密。
- /root/autodl-tmp 是默认 50GB 的本地数据盘。目录存在不代表已经正确挂载，必须用 findmnt、mountpoint、df 等验证。它 IO 高但无冗余，也不会进入系统镜像，适合当前工作集、缓存、输出和少量活跃模型，不能作为完整模型库或唯一备份。
- /root/autodl-fs 是多副本网络文件存储，可在同地区实例间共享且不受实例释放影响。它用于重要数据、代码备份、工作流和完整模型库；由于 IO 一般，当前需要的高 IO 数据可按空间情况暂存到本地数据盘。
- 保存镜像只包含系统盘。同地区克隆实例以系统盘为模板，并可选择额外复制本地数据盘；文件存储由同地区实例另行挂载。不要把“保存镜像”“克隆实例”“复制数据盘”视为同一个动作。
- AutoDL 对实例内 6006/6008 提供公网映射。判断 6006 问题时必须区分本地服务、监听地址和平台映射。
- 不得读取并回显 Mihomo 节点、订阅 URL、token、SSH 私钥或 secrets 内容。可以检查敏感文件是否存在、权限、大小和路径。
- 不要用 eval "$(autodl turbo)" 或修改 shell 启动文件来注入全局代理。Mihomo 应独立运行；需要联网的单个命令可使用进程级代理。

已知但必须重新验证的线索：
- Mihomo v1.19.20 曾安装在 /usr/local/bin/mihomo，本地混合代理预期为 127.0.0.1:7890。
- 当前代理配置默认位于 ~/.config/autodl-instance/mihomo/config.yaml；历史数据盘配置可能仍存在，只检查元信息。
- 先前代理初始化在下载 country.mmdb、geoip.dat、geosite.dat 时卡住并被中断。
- ComfyUI 曾显示 “To see the GUI go to: http://127.0.0.1:6006”，但 AutoDL 的 6006 公网 HTTP 地址返回通用 404。
- Torch 插件已恢复；独立环境默认 /root/.venvs/comfyui，实际安装状态必须验证。

请建立一个检查清单并依次完成：
1. 基础身份：pwd、Git root/branch/HEAD/status、OS、内核、CPU、内存、时区；保留用户已有改动。
2. 存储：用 findmnt -T、mountpoint、df -hT、df -i 验证 /root、/root/autodl-tmp、/root/autodl-fs 的真实挂载、容量和 inode。分别判断系统盘镜像内容、本地高 IO 工作集和文件存储可靠主库是否放置合理；只做浅层大小统计，避免全盘扫描。列出系统盘中的大目录和可能阻碍保存/共享镜像的秘密路径，但不要读取秘密内容。
3. GPU/CUDA：nvidia-smi、驱动版本、可见 GPU、CUDA 工具；分别记录系统能力和 Python 环境实际可用能力。
4. Python 环境：列出 conda、python、pip、uv、comfy、codex 的解析路径和版本；识别 base Conda、ComfyUI 虚拟环境以及项目环境，判断是否发生混用。不要安装 pytest 或依赖。
5. ComfyUI：检查 /root/ComfyUI 是否存在、Git 状态/版本、main.py、requirements、虚拟环境、custom_nodes、user、output、models，以及这些目录是否为正确软链接。只列目录和元数据，不读取工作流私密内容。
6. 进程与端口：用 ps、lsof、netstat 或可用等价工具确认 Mihomo、ComfyUI 的 PID、命令行、工作目录及 7890/9090/6006/6008 监听地址。缺少 ss 不应导致检查失败，也不要因此安装软件。
7. Mihomo：检查二进制版本、配置路径候选、PID/日志/GeoData 文件存在性和权限；禁止打印 config.yaml 内容。若 7890 正在监听，仅执行带明确代理的短超时 HEAD 请求验证 GitHub 连通性。
8. ComfyUI HTTP：使用明确绕过代理的 curl --noproxy '*' 对 127.0.0.1:6006 做短超时检查，记录状态码、Server 和 Location。若未监听，只报告，不启动。检查实际监听是否为 127.0.0.1 或 0.0.0.0。
9. 项目：只读检查配置解析出的 code_root、base_dir、workspace_dir、workspace_data_dir、comfy_dir、models_dir，并与真实文件布局比较。不要运行会调用 setup_network() 的入口。可以运行不会写入的静态导入或测试收集，但不得为此安装依赖。
10. 安全与恢复：检查 secrets/config 权限、关键数据是否只有单份、是否已有备份位置；不得展示秘密内容，也不要建议把明文秘密迁移到数据盘或文件存储。

最终用中文给出：
- 已验证的环境事实表，注明证据命令；
- ComfyUI、Mihomo、存储、Python/CUDA、6006 映射各自的结论；
- “实际路径 vs 项目预期路径”对照表，并提出系统镜像、本地工作集、文件存储主库之间的迁移建议；
- 系统盘是否适合保存个人镜像，以及共享前必须清理的敏感项清单；
- 按 P0/P1/P2 排序的问题，每项写清风险、证据和最小修复建议；
- 明确区分主机环境问题、AutoDL 平台问题和项目代码问题；
- 下一轮建议执行的最小任务列表。

不要把“未发现”写成“已正常”，无法验证的项目必须标为未验证。本轮完成报告后停止，等待我确认第二步。
```

## 后续会话的全局说明

首轮审计确认路径后，再让 Codex 将稳定事实合并到 `/root/.codex/AGENTS.md`。不要把当前 PID、临时错误、token、代理节点或公网 URL 写入全局说明。Codex 只在新会话启动时读取指令链，修改后需要退出并重新启动 Codex 才会生效。

建议保留的全局规则是：三层存储职责、镜像容量控制、先读后写、秘密保护、进程归属检查、非全局代理、真实挂载验证，以及“主机实测优先于文档默认值”。项目架构和测试命令继续由仓库内的 `AGENTS.md` 管理。

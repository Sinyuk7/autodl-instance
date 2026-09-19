# 实现逻辑

统一入口：src/cli.py 的 main，editable 安装提供 autodl 命令。

## init

合并已有配置和显式参数，补齐默认路径，验证受管存储挂载，创建数据目录并保存配置。然后初始化网络：优先配置的 Mihomo，健康进程复用；无配置时尝试 AutoDL 学术加速，否则直连。配置失败不回滚已创建目录。

Mihomo 配置固定在本机 config.yaml 同级的 mihomo 目录，默认 ~/.config/autodl-instance/mihomo。历史数据盘代理配置不会自动迁移，也不会自动停止不属于新配置的进程。

## setup

先构造上下文和验证挂载，再初始化网络并顺序执行：

1. system：系统工具、uv、独立 venv。复用可用 uv，不写 shell 配置。
2. comfy_core：在同一 venv 安装最新版 comfy-cli，用常规安装流程安装 ComfyUI 最新稳定版及其依赖。不维护依赖清单或版本锁定，不使用 fast-deps 或本机版本快照约束解析。依赖由 comfy-cli 和 ComfyUI requirements.txt 决定，安装后仅检查依赖一致性与 Torch 导入。环境内完成标记和现有 main.py 共同决定是否跳过；重复 setup 不自动升级已完成的 ComfyUI。
3. workspace：迁移 user/output 并创建软链接，同名冲突保留。
4. models：迁移模型并连接 models_dir，错误软链接或普通文件拒绝覆盖。

GPU 类型仅指定 NVIDIA，CUDA wheel 选择交给 comfy-cli，不在项目内固定。安装不以 GPU 可用为前提，不修改驱动或基础 Conda；GPU 推理需另行验证。

任何 setup 异常停止后续步骤，成功保存 artifacts。仅支持完整 setup/start/stop，不提供跳过依赖的局部执行参数。

## start / stop

start 用专用 venv 中的 comfy 启动，监听 0.0.0.0:6006，使用配置的 temp_dir。端口占用时报错，不杀未知进程。
stop 收集插件失败，再停止确认归属的代理；SIGTERM 超时报告失败，不自动 SIGKILL。

## download

autodl model download URL 交互选择文件名和相对目录；--preset 从 models/manifest.yaml 顺序下载。
所有目标必须位于 downloads_dir 内，拒绝绝对路径、.. 和越界软链接。已有未完成文件可续传。
先估算远端大小检查空间，大小未知会明确提示并继续；aria2 负责下载，缺失时尝试安装。
成功写隐藏 .meta，不自动复制到 models_dir、不更新 lock。批量存在失败则返回非零退出码。
帮助、list/status/types/cache list 不初始化网络；cache clear 只删除带 .aria2 的未完成文件。

## 配置

runtime.py 解析路径，环境变量覆盖本机配置，本机配置覆盖默认值（python_env_dir 通过本机配置指定）。
ComfyUI 环境默认 /root/.venvs/comfyui，必须位于系统盘，拒绝覆盖非 venv 目录。
默认 output_dir 为 /root/autodl-fs/ComfyUI/output；downloads/cache/temp 为 /root/autodl-tmp/ComfyUI 下同名目录。
安装成功不等于 GPU 推理已验证，真实 GPU、联网、模型加载和 AutoDL 公网映射需另行验证。

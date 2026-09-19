# 实现逻辑

统一入口：src/cli.py 的 main，editable 安装提供 autodl 命令。

## init

合并已有配置和显式参数，补齐默认路径，验证受管存储挂载。调用 `MigrationManager.initialize()` 的无冲突策略：保持 models/output 实体根目录，只对直接子目录迁移和链接，根目录文件和以 `.` 开头的直接子项不参与处理；状态检查使用同样过滤。普通目录内部隐藏文件仍计入非空判断并保留。源为空可链接到非空目标；目标缺失或为空可自动迁移；双方非空则警告跳过。配置未变不重写，安装前不创建 ComfyUI 源码目录。然后初始化网络，复用健康代理。
Mihomo 配置固定在本机 config.yaml 同级的 mihomo 目录，默认 ~/.config/autodl-instance/mihomo。历史数据盘代理配置不会自动迁移，也不会自动停止不属于新配置的进程。

## setup

先构造上下文和验证挂载，使用调用进程的网络环境并顺序执行：

1. system：系统工具、uv、独立 venv。复用可用 uv，不写 shell 配置。
2. comfy_core：在同一 venv 安装最新版 comfy-cli，用常规安装流程安装 ComfyUI 最新稳定版及其依赖。不维护依赖清单或版本锁定，不使用 fast-deps 或本机版本快照约束解析。依赖由 comfy-cli 和 ComfyUI requirements.txt 决定，安装后仅检查依赖一致性与 Torch 导入。环境内完成标记和现有 main.py 共同决定是否跳过；重复 setup 不自动升级已完成的 ComfyUI。

GPU 类型仅指定 NVIDIA，CUDA wheel 选择交给 comfy-cli，不在项目内固定。安装不以 GPU 可用为前提，不修改驱动或基础 Conda；GPU 推理需另行验证。

任何 setup 异常停止后续步骤，成功保存 artifacts。仅支持完整 setup/start/stop，不提供跳过依赖的局部执行参数。

## migrate

调用同一个 `MigrationManager.migrate()`，允许合并双方非空子目录并完成链接；不安装依赖、不初始化网络。`manager.py` 负责路径检查、锁、目录状态判断与策略，`transfer.py` 负责复制校验和带记录的自动迁移恢复，`merge.py` 负责显式冲突保留。`core/data_layout.py` 仅保留兼容导入，没有业务逻辑。

自动迁移的目标发布采用原子不覆盖操作；记录目标设备号/inode，恢复时核对归属和内容后才清理源文件。记录保存在 ComfyUI/.autodl-layout。所有数据写入者必须在迁移时停止；不把进程中断恢复描述为断电或存储故障下的数据持久性保证。user 沿用整目录显式合并策略，init 保留非空 user。models/output 根目录文件在两种策略下都不修改。

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
默认 output_dir 为 /root/autodl-fs/output；downloads/cache/temp 为 /root/autodl-tmp/ComfyUI 下同名目录。
安装成功不等于 GPU 推理已验证，真实 GPU、联网、模型加载和 AutoDL 公网映射需另行验证。

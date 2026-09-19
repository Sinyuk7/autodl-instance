# 主机交接

当前工作：CLI 使用系统盘源码的 editable 安装；init 每次开机准备目录、链接与代理；migrate 显式迁移已有数据且不建立链接；setup 仅安装程序和依赖，使用 /root/.venvs/comfyui 独立环境。依赖完全交给 comfy-cli / ComfyUI，不维护 Torch 或 CUDA 版本锁定。
完整历史现场数据可能过期，每次操作以实测为准。

已确认的设计：
- output_dir: /root/autodl-fs/ComfyUI/output
- downloads_dir: /root/autodl-tmp/ComfyUI/downloads
- cache_dir: /root/autodl-tmp/ComfyUI/cache
- temp_dir: /root/autodl-tmp/ComfyUI/temp
- 模型库默认 /root/autodl-fs/ComfyUI/models；旧本机配置可能仍指定本地盘，禁止默默迁移。
- user 默认仍为本地工作副本，重要工作流另存共享存储。
- 代理运行目录已按用户要求从 /etc/mihomo 迁至 ~/.config/autodl-instance/mihomo；/etc/mihomo 保留兼容软链接。迁移后曾验证代理可用；最新检查 PID 5167 已退出，代理请求未成功，直连 PyPI HTTP 200。需要代理时重新执行 init，不把旧 PID 当成运行状态。
- 数据盘遗留代理副本已移到 ~/.config/autodl-instance/mihomo-legacy-data-disk 保留；两份 config.yaml 权限均为 600，目录 700。
- 已创建 Python 3.12.3 的 /root/.venvs/comfyui，隔离检查通过；nvidia-smi 无执行权限，GPU 推理未验证。
- 旧 /root/.cache/uv 约 9.5G 已移至 /root/autodl-tmp/ComfyUI/cache/uv-legacy，原路径保留软链接，缓存可复用但不进入镜像。
- 已删除 torch_engine 插件、手工 CUDA 修补逻辑及所有 ComfyUI/Torch 安装版本锁定；安装命令使用 comfy-cli install --version latest --nvidia，其他依赖跟随上游。无 GPU 时当前 comfy-cli 默认选择 cu126。
- 本机版本快照方案已按用户要求取消；不要引入依赖快照、约束文件或项目自管的 Torch 安装步骤。
- 独立 venv 已安装当前上游最新稳定版 ComfyUI v0.36.0 所需依赖和 Manager。2026-09-20 按该版本 README 的 NVIDIA 安装说明，将本机修正为 Torch 2.14.0+cu130、torchvision 0.29.0+cu130、torchaudio 2.11.0+cu130，CUDA build 13.0、cuDNN 92400。这些是现场结果，不是项目锁定；项目安装策略仍委托 comfy-cli 和上游依赖文件。
- 新环境 pip check、隔离检查、Torch 三件套导入、CPU 张量运算通过；隔离 CPU 测试服务 127.0.0.1:8189 返回 HTTP 200，已用 SIGTERM 停止。未测试 GPU 推理。
- 上游当前存在无卡安装差异：comfy-cli 回退 cu126，但 ComfyUI v0.36.0 README 要求 NVIDIA 20 系及更新显卡使用 cu130+。本机已按上游说明完成一次性修复，版本警告消失；不要据此宣称 GPU 推理已验证，也不要把此次修复变成项目版本锁定。
- CUDA 13 安装计划先按上游索引解析，再从旧缓存及旧环境安装记录恢复缺失 wheel，实际切换全程离线完成，没有重新下载 Torch 大包，没有创建约束文件。
- 已卸载基础 Conda 中的旧 comfy-cli、ComfyUI 专用依赖及全部 Torch/Triton/CUDA/NVIDIA Python 包；Conda、Jupyter、共享依赖和系统驱动保留。基础环境 pip check、Jupyter 导入通过，原包可重新安装，旧 uv 缓存仍在数据盘。
- 已清理独立 venv 中无使用者的 CUDA 12 包。发现 cu12/cu13 的 cuDNN、cuSPARSELt、NCCL、NVSHMEM 包拥有重叠文件，卸载后已从缓存重装这四个 cu13 包，验证通过。不要直接卸载同路径的旧包而不修复保留包。
- pip 卸载留下的未登记 Torch 系列残余文件已移出基础 Python 搜索路径，保留于 ~/.local/share/autodl-instance/removed-*-files，可恢复。系统盘目前约 8.5G 已用、22G 可用；安装临时 wheel 和本轮测试目录已清理。
- CPU 测试触发上游用户数据库迁移，原 /root/ComfyUI/user/comfyui.db 已从 .bak 恢复，字节比较一致；.bak 保留。以后隔离测试还应显式指定独立 database-url，避免上游迁移默认数据库。
- 2026-09-20 清理后的 CPU 启动测试已显式指定独立 database-url，127.0.0.1:8189 返回 HTTP 200，测试服务已 SIGTERM 停止；原用户数据库未变。新旧环境 pip check 和项目 165 项测试通过。
- 一次性打包缓存和测试目录已清理；模型、输出、工作流目录未执行真实 setup 迁移。ComfyUI 安装完成标记已记录，GPU 验证独立进行。
- 修复共享存储软链接误判：/root/autodl-fs 是指向 /autodl-fs/data 的软链接，Path.is_mount() 必须检查解析后的真实路径。主机真实挂载检查与上下文创建通过，项目测试 165 项通过。

后续真实安装前：
1. 读 Git status，保留未提交变更。
2. 用 findmnt -T、mountpoint、df -hT、df -i 重验两块存储及系统盘容量。
3. 核对实际 GPU/驱动、ComfyUI 路径、Python 环境和监听进程。
4. 独立 venv 由 setup 创建；不要在 base Conda 中安装依赖。
5. setup 仅安装程序和依赖，使用调用进程网络；init 会准备目录／链接并初始化代理，migrate 会搬迁数据。三者均不能用来探测状态。
6. 真实下载、GPU 推理和公网映射必须分别验证。

禁止打印秘密或未经要求 commit/push；镜像操作由用户在 AutoDL 控制台执行。

- 本次职责拆分仅修改代码和文档并执行隔离测试；未执行主机 init/setup/migrate，现有数据布局和本机路径配置未修改。
- 职责拆分后隔离测试 182 项通过；原子不覆盖迁移在临时目录验证，共享存储支持情况尚未实测，不支持时保留源文件并报错。

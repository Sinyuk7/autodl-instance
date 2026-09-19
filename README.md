# autodl-instance

AutoDL 上的 ComfyUI 环境、代理和模型管理工具。

## 安装

在现有源码目录执行（需要 uv）：

```bash
cd /root/autodl-instance
uv tool install --editable --force .
autodl --help
```

CLI 直接使用当前源码。修改 Python 文件后立即生效；修改依赖后重新执行安装命令。

## 使用

先确认本地数据盘和文件存储已挂载：

```bash
findmnt -T /root/autodl-tmp
findmnt -T /root/autodl-fs
mountpoint /root/autodl-tmp
mountpoint /root/autodl-fs
df -hT /root /root/autodl-tmp /root/autodl-fs
df -i /root /root/autodl-tmp /root/autodl-fs
```

```bash
autodl secrets set mihomo-subscription-url  # 使用 Mihomo 时配置；交互输入
autodl init       # 每次开机：检查挂载、创建缺失目录、建立安全链接、初始化代理
autodl status     # 只读检查
autodl setup      # 新实例首次安装：仅安装程序和依赖
autodl migrate    # 显式合并双方非空的子目录，保留冲突并建立链接
autodl init       # 安装后及日后每次开机执行
autodl start      # 前台启动，监听 0.0.0.0:6006
autodl stop       # 停止确认归属的 ComfyUI 和代理进程
```

已有配置在重复 init 时保留，显式参数可覆盖；配置未变时不重写配置文件。健康 Mihomo 会复用。ComfyUI 尚未安装时只准备存储目标，不创建源码目录。

`init` 和 `migrate` 共用 `src/lib/migration` 模块。models/output 根目录保持为实体目录，仅管理其直接子目录：

| ComfyUI 子项 | 共享存储同名子项 | init 行为 |
|---|---|---|
| 不存在或空目录 | 实体目录（可有文件） | 建立链接；已有目标数据不动 |
| 非空目录 | 不存在或空目录 | 复制校验、迁移并建立链接 |
| 非空目录 | 非空目录 | 报告并跳过；由 migrate 显式合并 |
| 正确链接 | 正常目标 | 跳过 |
| 错误链接、失效链接、文件占位或目标链接 | 任意 | 保留并报告，不自动改写 |

两边 models/output 根目录的普通文件均不迁移、不覆盖、不去重。根目录下以 `.` 开头的隐藏项（如 `.ipynb_checkpoints`）不参与迁移、链接或链接状态检查，已有隐藏项原样保留。普通子目录内部的隐藏文件和占位文件仍算内容，迁移时保留，不将这些目录误判为空。仅右边有的子目录会在左边建立链接，新建的本地子目录下次 init 再处理。`checkpoint` 和 `checkpoints` 不会自动合并。直接写入本地 output 根目录的图片仍在系统盘；需要持久化输出时应写到已链接的子目录。旧版整个 models/output 根目录的正确软链接保留并提示，不自动转换。

user 保持原有整目录策略：init 遇到非空 user 保留并提示，不阻塞 models/output；migrate 可显式合并 user 后链接。
setup 不初始化代理、不迁移数据、不建立数据链接。init 的代理环境仅作用于自身进程；安装需要代理时可使用单命令环境，例如 `HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890 NO_PROXY=127.0.0.1,localhost autodl setup`（端口以实际配置为准）。

migrate 对双方非空的子目录合并，保留目标文件；同内容源副本去重，不同内容源文件另存 `.autodl-model-conflicts` 或 `.autodl-migration-conflicts`，已有冲突副本追加编号。之后完成链接。根目录文件同样不处理。

自动整子目录迁移使用临时目录、SHA-256 内容校验、原子不覆盖发布和 ComfyUI 下 `.autodl-layout` 恢复记录。复制失败保留源文件；发布／清理／链接阶段中断后再次运行可恢复，仅接管记录中属于本次迁移的目标。恢复记录和临时目录不要手动删除。文件系统不支持原子不覆盖时会报错。目录内包含软链接或特殊文件时自动迁移停止，需手动处理。锁防止本工具多个迁移同时运行，但不能阻止 ComfyUI 或其他实例写入；init/migrate 迁移期间必须停止数据写入。测试验证了进程中断恢复，不保证整个流程是跨目录事务或可抵抗存储故障。

首次安装使用最新版 comfy-cli 和 ComfyUI 最新稳定版，依赖跟随 ComfyUI 自己的 requirements.txt；项目不维护依赖版本锁定。无卡也可安装，GPU 推理需有卡后验证。

## 模型

```bash
autodl secrets set hf-token               # 需要认证时设置
autodl model download 'https://huggingface.co/组织/仓库/resolve/main/模型.safetensors'
autodl model download --preset FLUX.2-klein-9B
autodl model list
```

模型先下载到 downloads，完成后生成隐藏的 .meta 文件。确认文件后，将模型和 .meta 一起手动移入模型库；不会自动发布或更新 model-lock.yaml。HuggingFace 使用文件的 resolve 地址。

## 默认路径

| 内容 | 路径 |
|------|------|
| ComfyUI 源码 | /root/ComfyUI |
| 独立 Python 环境 | /root/.venvs/comfyui |
| 模型库 | /root/autodl-fs/models |
| 输出 | /root/autodl-fs/output |
| 下载暂存 | /root/autodl-tmp/ComfyUI/downloads |
| 缓存 | /root/autodl-tmp/ComfyUI/cache |
| 临时文件 | /root/autodl-tmp/ComfyUI/temp |
| user 工作目录 | /root/autodl-tmp/comfyui-workspace/user |
| 本机配置与代理 | ~/.config/autodl-instance/ |

本地盘在实例释放后丢失，重要工作流需另存文件存储。秘密留在系统盘，代理配置使用 600 权限。旧本机配置可能覆盖默认路径，可用 `autodl config show` 检查。

更多：[开发说明](CONTRIBUTING.md) · [实现逻辑](src/README.md) · [测试](tests/README.md)

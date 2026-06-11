# 项目 Review 报告

> 版本：v2（基于作者反馈修正）
> 修正要点：
> - 删除"自动模型恢复"作为目标。lock 是清单 + 指纹，不是下载源。
> - 大模型（20-30GB）下载永远是用户主动行为。
> - aria2 是实测后选定的最优策略，HF Hub / hf_xet 在 AutoDL 实测无法连接。

## 1. Executive Summary

1. **lock 文件的真正定位是"清单 + 指纹"**，不是恢复触发器。当前架构基本对齐这个定位，但有路径 bug 让能力打折。
2. **model-lock.yaml 路径不一致（P0）**：`GenerateSnapshotTask` 写到 `ctx.base_dir / model-lock.yaml`，`config.py:LOCK_FILE` 读的是 `PROJECT_ROOT / my-comfyui-backup / model-lock.yaml`。`model status` 永远读不到 sync 写的快照。
3. **lock 文件不在 Git 同步范围（P0）**：写到数据盘根，不在 `my-comfyui-backup/` 内，实例释放即丢失，跨实例没法看清单。
4. **缺失"清单 → 缺失检测 → 引导下载"链路**：用户在新实例上无法用一条命令看到"我之前有 X 个模型，现在还缺 Y 个，建议执行哪些 `model download` 命令"。
5. **缺 status / doctor 能力**：软链接是否健康、模型 hash 是否漂移、节点是否齐全，全靠用户跑起来才发现。
6. **README 下载策略描述错误**：声称 HF 用 `huggingface_hub + hf_xet`，实际只有 aria2。aria2 是实测最优，应修正描述而非"恢复 HF Hub 策略"。
7. **网络子系统是项目最成熟模块**：mihomo + turbo fallback、跨进程状态缓存、订阅失败缓存、配置漫游。不要动。
8. **数据盘 / 系统盘边界整体正确**，但 README 声称的 `.cache` 迁移在代码中找不到实现，文档与代码不一致。
9. **lock.py 与 GenerateSnapshotTask 代码重复**：两份几乎相同的扫描 / 增量 hash 逻辑，且 Task 版本丢了 `.meta` sidecar 合并。
10. **模型清单价值被低估**：当前 lock 只用于"sync 时记录"，没有"setup 后展示"、"start 前检查"、"导出购物清单"等下游消费场景。

---

## 2. 我对项目的理解

### 项目当前做什么

7 个插件、3 个生命周期阶段：

| 阶段 | 命令 | 做什么 |
|------|------|--------|
| `setup` | `./init.sh` | uv → Git/SSH → PyTorch → ComfyUI → user 软链接 → 节点恢复 → models 软链接 |
| `start` | `start` | 释放端口 → 启动 ComfyUI（127.0.0.1:6006） |
| `sync` | `bye` | 逆序：模型快照 → 节点快照 → user git push → mihomo 配置同步 |

独立 CLI `model` 用于交互式下载、批量预设下载、缓存管理。

### 项目想解决什么

README：**Infrastructure as Code + User Data Roaming**。

### 项目真正应该解决什么（修正后）

在 AutoDL 这种"实例可被释放、模型几十 G 不能自动重下"的约束下：

1. **环境基础设施**自动恢复（uv、Comfy、节点、配置）—— 已基本做到
2. **创作资产（workflow / 配置 / 节点快照 / 模型清单）**跨实例漫游 —— 已基本做到
3. **大资产（模型本身）**靠用户主动管理，但工具要：
   - 让用户清楚知道"我之前有什么"
   - 让用户清楚知道"我现在缺什么"
   - 给出"如果要恢复，应该执行哪些命令"
   - 让"批量下载（preset）"足够简单，但**永远由用户触发**
4. **诊断能力**让用户在出问题时不抓瞎

### 文档与源码一致性

| 方面 | 一致性 | 说明 |
|------|--------|------|
| README 下载策略表 | ❌ | 声称 HF 用 `huggingface_hub + hf_xet`，实际只有 aria2（且 aria2 是实测最优） |
| README 缓存迁移 | ❌ | 声称迁移 `.cache`，代码无此逻辑 |
| CONTRIBUTING 网络模块 | ⚠️ | 引用 `src/lib/network.py`（单文件），实际是 `src/lib/network/` 包 |
| 插件架构 | ✅ | 顺序、生命周期、配置加载与代码吻合 |
| model-lock.yaml 位置 | ❌ | example、写入路径、读取路径三者不一致 |

---

## 3. AutoDL 背景下的核心问题

### 做到了什么

| 能力 | 状态 |
|------|------|
| 系统盘 / 数据盘软链接 | ✅ models / output / user / SSH |
| 无卡模式初始化 | ✅ TorchAddon 检测无 GPU 时跳过驱动校验 |
| 网络加速 | ✅ mihomo + turbo + HF mirror + token，带 fallback |
| 端口处理 | ✅ release_port + 监听 127.0.0.1:6006 |
| 进程清理 | ✅ kill_process_by_name |
| 幂等 setup | ✅ FileStateManager + StateKey |
| 跨实例数据漫游 | ✅ 通过 userdata_repo（user / script_examples） |

### 没做到 / 不清楚的地方

| 缺失 | 影响 | 严重度 |
|------|------|--------|
| **新实例感知** | 没有机制区分"新实例 + 数据盘空"和"老实例重启"。`.autodl_state/*.done` 在数据盘，数据盘没了所有标记一起消失，会跑全量 setup（这其实是正确行为），但**用户视角无法清楚知道"我现在处于哪种场景"** | 🟡 |
| **`.cache` 迁移** | README 声称做了但代码没做。pip / uv / huggingface_hub 缓存堆在系统盘，长期可能撑爆 | 🟡 |
| **磁盘空间预检** | 模型下载、节点克隆前不检查剩余空间 | 🟡 |
| **`model-lock.yaml` 不在 Git 同步范围** | 实例释放 → 清单丢失 → 用户无法回看"我之前有什么" | 🔴 |
| **start 前不做完整性检查** | workflow 跑起来才报"模型缺失"，浪费 GPU 时间 | 🟡 |

---

## 4. AIGC / ComfyUI 工作流背景下的核心问题（重写）

### 重新校准定位

> **这个工具不下载模型给用户，工具只让用户自己下载得更顺手、更清楚。**

模型下载是用户行为，不是工具行为。原因：
- 单模型 5–30GB，多模型 50–100GB+
- 网络抖动 / 限速 / 鉴权失败时间长
- 用户对"现在要不要下"有自己的判断（要不要省钱、是不是临时启动、用哪个 preset）

工具应该围绕**让用户做判断和触发**来设计。

### 已有能力（保留）

| 能力 | 状态 | 评价 |
|------|------|------|
| `model download <url>` 交互式 | ✅ | 文件名 / 类型 / 子目录全程引导，是项目的精华 |
| `model download -p <preset>` 批量 | ✅ | 一个 workflow 所需模型一次触发，幂等跳过已存在 |
| Civitai URL 自动解析 | ✅ | 自动识别 type / base_model / filename |
| HuggingFace 镜像 + Token 注入 | ✅ | 走 hf-mirror.com + Bearer header |
| `aria2` 多线程下载 | ✅ | 实测最稳，HF Hub / xet 在 AutoDL 不可用 |
| `.meta` sidecar 记录来源 | ✅ | 每个文件留下 url / source / downloaded_at |
| `model-lock.yaml` 快照（sync 时） | ✅ | 记录 path / hash / type，增量 hash |
| 节点快照恢复 | ✅ | comfy node restore-snapshot |
| 节点依赖自动安装 | ✅ | 遍历 custom_nodes/*/requirements.txt |
| 用户配置 / workflow 漫游 | ✅ | user/ 软链接 + git |

### 真正缺的能力（重写）

| 缺失 | 价值 | 实现思路 |
|------|------|----------|
| **lock 跨实例可见** | 用户在新实例 `model status` 就能看到旧实例有什么 | 修复 lock 路径 + 进 git 同步（P0） |
| **缺失模型清单（diff）** | 一眼看出"现在缺哪些"，给出建议下载命令 | `model status` 增加 `lock vs 实际` diff |
| **start 前完整性检查** | 启动前提示"X 个模型缺失，是否继续"，不让 workflow 跑起来才发现 | ComfyAddon.start 前调用 status check |
| **preset 与 lock 的关联** | 用户能选择"按 preset 恢复"还是"按 lock 恢复"，但**始终是用户决定** | `model status --preset` 显示 preset diff |
| **导出购物清单** | 用户想换平台 / 备份到外部 NAS 时，能导出一份"模型 url 列表" | `model export` 输出 .txt 或 rclone 兼容格式 |
| **模型完整性校验（hash）** | 检测下载是否损坏 / 被覆盖 | `model verify` 跑 sha256 对比 lock |
| **workflow → 模型依赖映射** | 打开一个 .json workflow 时知道它依赖哪些模型 | 解析 workflow 节点中的模型引用（中长期） |
| **外部存储辅助** | 用户自己有 OSS / 网盘 / NAS，工具能配合 rsync / rclone | 提供 `model export-list` 让外部脚本消费 |

### 关键判断（修正）

项目目前是 **"安装器 + 主动下载器"**，应该升级为 **"安装器 + 主动下载器 + 清单可视化 + 缺失诊断"**。

模型本身的备份责任在用户（外部存储 / 网盘 / 公开来源）。工具的责任是：
- **可见**：永远能告诉用户"曾经有什么、现在缺什么"
- **可触发**：手动下载命令尽量短、参数尽量少
- **不越权**：绝不在 setup / start 流程中自动 5–30GB 下载

---

## 5. 当前问题清单（修正）

### P0：必须先处理

#### P0-1: model-lock.yaml 三处路径不一致
- **来源**：
  - `GenerateSnapshotTask._get_lock_file_path()` → `ctx.base_dir / "model-lock.yaml"` = `/root/autodl-tmp/model-lock.yaml`
  - `addons/models/config.py:LOCK_FILE` → `PROJECT_ROOT / "my-comfyui-backup" / "model-lock.yaml"`
  - `my-comfyui-backup.example/model_lock.yaml`（文件名带下划线，不一致）
- **影响**：`model status` 永远读不到 sync 写的快照；新实例 git clone userdata repo 后也找不到 lock
- **方向**：统一到 `my-comfyui-backup/model-lock.yaml`（用连字符），写入和读取都走这条路径

#### P0-2: model-lock.yaml 不在 Git 同步链路
- **来源**：当前写入路径在 `my-comfyui-backup/` 之外
- **影响**：实例释放后 lock 丢失，跨实例完全失去清单价值
- **方向**：把写入位置移进 `my-comfyui-backup/` 后，userdata addon 的 `git add .` 自动捕获，无需额外配置

#### P0-3: lock.py 与 GenerateSnapshotTask 重复实现
- **来源**：`src/addons/models/lock.py` 已有 `scan_models / generate_snapshot / read_meta`，`GenerateSnapshotTask` 又独立实现一遍且丢了 `.meta` 合并
- **影响**：双源真相，且 Task 版本快照里没有 `url / source` 信息，**直接削弱"清单"价值**（用户看到 lock 也不知道当时从哪下的）
- **方向**：Task 调用 `lock.py` 函数，删除 Task 内部重复代码

### P1：应该处理

#### P1-1: 缺失 `model status` 的 diff 能力
- **现状**：`model status` 只列 lock 中记录的模型 + 显示是否存在
- **缺**：不告诉用户"lock 里有但本地没有的"是哪些（最有价值的部分）；不显示 hash 是否漂移
- **方向**：扩展输出三类
  - ✅ 存在且 hash 一致
  - ⚠️ 存在但 hash 不一致（被改 / 被覆盖）
  - ❌ lock 里有但本地缺失 + 给出建议命令（`model download <url>`）

#### P1-2: 无 `status` / `doctor` 命令
- **缺**：软链接健康、磁盘空间、节点齐全、网络可用性，全靠用户感知
- **方向**：新增 `status`（快速概览）和 `doctor`（深度检查）两条命令

#### P1-3: README 下载策略描述错误
- **现状**：声称 HF 用 `huggingface_hub + hf_xet`，实际只有 aria2
- **方向**：直接改 README 描述为 "所有 URL 统一走 aria2 多线程"，并补一句"实测在 AutoDL 网络环境下 aria2 比官方 SDK 稳"

#### P1-4: README 声称的 `.cache` 迁移未实现
- **现状**：代码中 `SystemAddon` 没有迁移逻辑
- **方向**：要么实现（系统盘 `~/.cache` 软链接到数据盘），要么从 README 删除该承诺

#### P1-5: setup 失败后无清晰恢复指引
- **现状**：`.autodl_state/*.done` 标记可能停在中间
- **方向**：增加 `--reset [<addon>]` 选项；或每个插件 setup 开头做"实际状态校验"而非只信任 done 文件

### P2：后续优化

| ID | 问题 | 方向 |
|----|------|------|
| P2-1 | ComfyUI 监听 127.0.0.1，需确认 AutoDL 端口映射兼容性 | 实测验证，必要时改 0.0.0.0 |
| P2-2 | 节点依赖用 `pip` 不用 `uv` | 统一到 `uv pip install --system` |
| P2-3 | 下载前不校验磁盘空间 | aria2 启动前 statvfs 检查 |
| P2-4 | CONTRIBUTING.md 网络模块引用过时 | 改 `src/lib/network.py` → `src/lib/network/` |
| P2-5 | start 前不做模型缺失提示 | 调用 `model status` 的 diff 能力，但不阻断启动（仅提示） |
| P2-6 | `model export` 缺失 | 输出 url 列表（txt / json），方便外部脚本 / rclone 消费 |
| P2-7 | `model verify` 缺失 | 对比 lock hash 检测损坏 |

### P3：暂时不管

| ID | 问题 |
|----|------|
| P3-1 | SECURITY.md 是占位符模板 |
| P3-2 | pluggy 引入但实际没用 PluginManager（只是装饰器） |
| P3-3 | 仓库里有 `src/__init__.pyc` |

---

## 6. 产品定位建议（修正）

### 定位 A：可靠的 AutoDL 初始化脚本（保守）
保持个人脚本属性，只修 bug、补文档。

### 定位 B：AutoDL ComfyUI 工作站管理器（推荐 ⭐）
增量补齐"清单可见性 + 缺失诊断 + 手动下载引导"，**绝不引入自动批量下载**。

核心能力栈：
1. 一键初始化（已有）
2. 主动下载（已有，体验已经很好）
3. **清单可见 / 缺失诊断**（要补）
4. **健康检查 / 诊断**（要补）
5. 用户数据漫游（已有）
6. 关机同步（已有）
7. 外部备份辅助（要补：export 命令）

### 定位 C：跨平台 AIGC 云工作区
通用化抽象，覆盖 Vast.ai / RunPod 等。投入产出比低，不推荐当前阶段。

**推荐：定位 B。** 不动核心架构、不引入自动下载、围绕"信息可见性"做加法。

---

## 7. 架构重构方向

### 需要理清的边界

1. **`lock.py` 是唯一真相** —— `GenerateSnapshotTask` 不再独立实现扫描逻辑
2. **lock 文件路径单一来源** —— `config.py:LOCK_FILE` 是唯一定义，Task 用同一常量
3. **lock 是 sync 的产出 + status 的输入** —— 明确这两个消费方，其它流程不读 lock

### 需要拆 / 合的模块

| 操作 | 对象 | 理由 |
|------|------|------|
| 合 | `lock.py` + `GenerateSnapshotTask` | 消除重复 |
| 拆 | `downloader.py`（500 行） | CLI 解析 / 命令实现 / 下载执行混在一起 |
| 不动 | `src/lib/network/` | 最成熟模块 |
| 不动 | 7 个插件硬编码顺序 | 显式优于隐式 |
| 不动 | AppContext + Artifacts | 强类型 DTO 设计合理 |

### 应先补测试的地方

1. **sync 链路**：当前 integration 测试覆盖薄
2. **lock diff / status 命令**：新增能力前先写测试
3. **网络 fallback 链**：mihomo → turbo 降级路径

### 高风险重构

1. **把 ComfyUI 安装到数据盘** —— comfy-cli workspace + Python 路径牵涉广，风险高
2. **替换 pluggy / argparse** —— 收益小

---

## 8. 用户路径重构方向（修正）

### 第一次使用
| 步骤 | 现状 | 改进 |
|------|------|------|
| clone + `./init.sh` | ✅ | 结尾打印"配置向导"提示 secrets / userdata_repo |
| 下载模型 | ✅ | 无 |
| `start` | ✅ | 启动前提示缺失模型（不阻断） |

### 日常启动
| 步骤 | 现状 | 改进 |
|------|------|------|
| `start` | ✅ | 启动前 1 秒做软链接 + 模型 diff 检查 |

### 下载模型
| 步骤 | 现状 | 改进 |
|------|------|------|
| `model download <url>` | ✅ | 无 |
| `model download -p <preset>` | ✅ | 无 |
| `model status` | ⚠️ 路径 bug | 修复路径 + 增加 diff 三态显示 |
| `model verify` | ❌ 缺失 | 新增 |
| `model export` | ❌ 缺失 | 新增（输出 url 清单） |

### 关机前
| 步骤 | 现状 | 改进 |
|------|------|------|
| `bye` | ✅ | 输出本次同步摘要（lock 增/减、git push 结果） |

### 新实例恢复（重写）
| 步骤 | 现状 | 改进后 |
|------|------|--------|
| `clone + init.sh` | ✅ 自动 | ✅ 自动 |
| 节点恢复 | ✅ 自动（快照） | ✅ |
| workflow 恢复 | ✅ 自动（git） | ✅ |
| **看到模型清单** | ❌ lock 丢失 | ✅ 修复后从 git 同步过来 |
| **知道缺什么** | ❌ 无 diff | ✅ `model status` 显示三态 |
| **下载模型** | ⚠️ 完全靠记忆 | ⚠️ 仍是手动，但有清单引导 + preset 一键触发 |
| **从外部备份恢复** | ❌ 无支持 | ✅ `model export` 给出 url 列表，用户用 rclone / wget / 自建脚本 |

**关键原则**：恢复链路里**永远没有自动下载**。工具只让用户的"手动恢复"更顺、更短、更清楚。

### 出错诊断
| 步骤 | 现状 | 改进 |
|------|------|------|
| 看日志 | ⚠️ `/root/autodl-tmp/autodl-setup.log` 但用户不知 | 增加 `model logs` / `start --tail-log` |
| 健康检查 | ❌ | 增加 `doctor` 命令 |

---

## 9. 数据与配置重构方向（修正）

### 数据分类表

| 类别 | 数据 | 当前位置 | 进 Git？ | 数据盘？ | 丢失影响 |
|------|------|----------|---------|----------|----------|
| 用户配置 | comfy.settings.json 等 | `user/` 软链接到 `my-comfyui-backup/user/` | ✅ userdata repo | ✅ | 重新配置 |
| 工作流 | `*.json` | `user/default/workflows/` | ✅ userdata repo | ✅ | 创作丢失 ⚠️ |
| 节点快照 | `*_snapshot.json` | `user/__manager/snapshots/` | ✅ userdata repo | ✅ | 节点需重装 |
| **模型清单** | `model-lock.yaml` | ⚠️ 路径错位 | ✅（修复后） | ✅（修复后） | **不知道之前有什么** |
| 模型 .meta | `.xxx.meta` | 与模型同目录 | ❌ 太多 | ✅ | 丢失下载来源 |
| 模型本体 | `.safetensors` 等 | `/root/autodl-tmp/models/` | ❌ 太大 | ✅ | **靠用户外部备份 / 重新下载** |
| secrets | 3 个 secrets.yaml | 分散在模块目录 | ❌ gitignored | ⚠️ 在代码目录 | 重新配置 |
| 运行状态 | `.autodl_state/*.done` | 数据盘 | ❌ | ✅ | setup 重跑 |
| Artifacts | `.artifacts.json` | 项目根 | ❌ gitignored | ✅ | start/sync 重新生成 |
| 网络缓存 | `/tmp/autodl_network_state.json` | /tmp | ❌ | ❌ 临时 | 自动重建（设计如此） |
| mihomo 配置 | config.yaml + cache.db | `/etc/mihomo/` ↔ `my-comfyui-backup/mihomo/` | ✅ userdata repo | ✅ | 重新配置代理 |
| aria2 控制文件 | `*.aria2` | 与下载文件同目录 | ❌ | ✅ | 失去断点续传 |
| bin 脚本 | start/bye/model/turbo | `bin/` | ❌ gitignored | ✅ | setup 重新生成 |
| 日志 | `autodl-setup.log` | 数据盘 | ❌ | ✅ | 失去调试历史 |

### Lock 文件的明确职责（新）

| 用途 | 是否当前支持 | 是否应该支持 |
|------|--------------|--------------|
| sync 时记录现状 | ✅ | ✅ |
| status 显示曾有什么 | ⚠️ 路径 bug | ✅ |
| status 显示缺什么 | ❌ | ✅ |
| 检测 hash 漂移 | ❌ | ✅ |
| 导出 url 清单给外部脚本 | ❌ | ✅ |
| **作为自动下载源** | ❌ | **❌（明确不做）** |

---

## 10. 分阶段重构计划（修正）

### Phase 0：理解与冻结（1–2 天）
- 在真实 AutoDL 实例上跑完整链路，记录每步真实输出
- 验证 model-lock.yaml 实际写入位置
- 验证 `model status` 是否能读到 lock
- 记录所有外部依赖版本（comfy-cli / uv / aria2）

### Phase 1：文档与定位修正（1–2 天）
- 修正 README 下载策略描述（aria2 是有意选定）
- 修正 README `.cache` 迁移描述（删除或实现）
- 修正 CONTRIBUTING.md 网络模块路径
- 在 README 增加章节明确"模型恢复永远是手动"的设计原则

### Phase 2：修复 Lock 三连 Bug（2–3 天）
- **P0-1**：统一 lock 路径到 `my-comfyui-backup/model-lock.yaml`
- **P0-2**：验证 git add . 能捕获 lock 文件
- **P0-3**：合并 lock.py 与 GenerateSnapshotTask
- 加单元测试覆盖：路径常量、读写一致、增量 hash、.meta 合并

### Phase 3：补 Status / Doctor（3–5 天，核心价值提升）
- `model status` 增加三态 diff（一致 / 漂移 / 缺失）
- 缺失项给出"建议下载命令"清单（基于 .meta 中的 url）
- 新增 `status`（项目级健康检查：软链接 / 磁盘 / 网络）
- 新增 `doctor`（深度检查 + 修复建议）
- start 前可选地运行 status 提示

### Phase 4：导出与外部协作（2–3 天）
- `model export`：导出 url 清单（txt / json / rclone 兼容）
- `model verify`：sha256 对比 lock
- 文档增加"外部备份恢复指南"章节（rsync / rclone / 网盘）

### Phase 5：长期维护（持续）
- 在真实 AutoDL 上演练完整恢复（释放旧实例 → 新实例 init → status 看清单 → 用户手动 download）
- 编写灾难恢复指南
- 建立 changelog

---

## 11. 第一批建议做的事情（修正）

按低风险高收益排序：

1. **P0-1：修复 model-lock.yaml 三处路径不一致** —— 改 1–2 个常量
2. **P0-2：把 lock 写入移进 `my-comfyui-backup/`** —— 让 git 同步自动覆盖
3. **P1-3：修正 README 下载策略描述** —— 5 分钟改文字，明确 aria2 是实测最优
4. **P0-3：合并 lock.py 与 GenerateSnapshotTask 的扫描代码** —— 减少双源真相
5. **P1-1：扩展 `model status` 显示三态 diff** —— 100 行内的核心价值提升
6. **`model status --hint`：缺失模型给出建议命令** —— 体验提升大
7. **P1-4：明确 `.cache` 迁移的状态**（实现或从 README 删除） —— 文档可信度
8. **P2-2：节点依赖统一用 uv** —— 一行改动
9. **`init.sh` 结尾输出配置向导提示** —— 新用户体验
10. **删除 `src/__init__.pyc` + 加进 .gitignore** —— 仓库整洁

---

## 12. 明确不要做的事情（修正）

1. **不要在 setup / start 流程中自动下载模型** —— 5–30GB 自动下载是反人类设计
2. **不要把 lock 文件设计成"恢复触发器"** —— lock 是清单 + 指纹，不是任务源
3. **不要恢复 huggingface_hub / hf_xet 策略** —— 实测在 AutoDL 不可用，aria2 是有意选择
4. **不要一上来全仓重写** —— 现有架构基本对，问题集中在路径一致性和清单可见性
5. **不要为架构漂亮破坏一键体验** —— `./init.sh` 简单是核心 UX
6. **不要把个人工具硬做成通用平台**
7. **不要把模型本体 / 大缓存进 Git**
8. **不要把 secrets 放进 manifest 普通字段**（SSH key Base64 那条要在文档说明风险）
9. **不要忽略实例释放风险** —— 所有只在系统盘的状态视为临时
10. **不要替换 pluggy / argparse / Rich** —— 当前选型够用
11. **不要在没真实跑过的情况下重构 ComfyUI 安装位置**

---

## 附录：Lock 文件的产品视角设计原则

> 模型本体的备份责任在用户（外部存储 / 网盘 / 公开来源）。
> 工具的责任是让用户的**手动管理**变得**有据可查、缺失可见、操作简短**。

| 职责 | 谁负责 |
|------|--------|
| 模型本体的存储与备份 | 用户（NAS / OSS / 网盘） |
| 模型清单（曾经有什么） | 工具（`model-lock.yaml`） |
| 模型指纹（是否一致） | 工具（sha256） |
| 模型来源（从哪下的） | 工具（`.meta` sidecar） |
| 触发下载 | **永远是用户** |
| 选择下载哪些 | **永远是用户**（preset 是预设清单，触发仍是用户） |
| 提供"购物清单"格式 | 工具（`model export`） |
| 检测缺失 / 漂移 | 工具（`model status`） |

这条边界清晰下来之后，工具的产品定位就稳了：
**AutoDL ComfyUI 工作站管理器：基础设施自动化 + 创作资产漫游 + 模型清单可视化。**

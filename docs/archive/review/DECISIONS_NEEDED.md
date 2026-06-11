# Decisions Needed

## Q1. ComfyUI 安装在系统盘还是数据盘？

现状：`src/main.py:32-33` 把 `BASE_DIR` 固定为 `/root/autodl-tmp`，`COMFY_DIR` 固定为 `/root/ComfyUI`；`ComfyAddon.setup()` 用 `comfy --workspace /root/ComfyUI install`，只有 `output` 和 `models` 被软链到数据盘。

方向 A：保持系统盘安装，只确保用户数据、模型、输出、lock 在数据盘或 Git。
- 代价：实例释放后要重装 ComfyUI/依赖。
- 收益：当前代码改动小，符合一键 `init.sh`。

方向 B：把 ComfyUI 安装到 `/root/autodl-tmp/ComfyUI`。
- 代价：workspace 路径、`.artifacts.json`、comfy-cli、节点依赖、磁盘空间都要重测。
- 收益：实例未释放但系统盘重置时更稳。

倾向：A。先不要迁移 ComfyUI 本体，除非真实冷启动重装时间成为主要痛点。

作者拍板：是否接受系统盘 ComfyUI 可丢失，只保证数据盘和 Git 中的创作资产可恢复？

## Q2. 是否提供 Web UI 仪表板？

现状：所有交互在 CLI；README 的目标是 `init.sh`、`start`、`bye`、`model`。

方向 A：不做 Web UI，先做 `status`/`doctor` 的 Rich CLI。
- 代价：视觉弱，不能点选。
- 收益：低成本、可在 SSH/Jupyter 终端直接用。

方向 B：做本地 Web dashboard。
- 代价：新增长驻后端、端口、安全、AutoDL 自定义服务冲突。
- 收益：模型状态和恢复链路更直观。

倾向：A。当前首要问题是事实可见，不是交互容器。

作者拍板：是否明确 2026 Q2 不做 Web UI？

## Q3. 是否提供模型仓库 / 索引？

现状：`src/addons/models/manifest.yaml` 只有项目内 preset；`model-lock.yaml` 应是曾经有什么，不是下载任务源。

方向 A：只维护个人 preset + lock，不做公共索引。
- 代价：发现模型仍靠用户。
- 收益：避免内容维护、版权、失效链接和自动下载误导。

方向 B：引入模型索引/仓库。
- 代价：维护成本高，容易变成低质量 SaaS/平台。
- 收益：新用户找模型更方便。

倾向：A。可以做 `model export-list`，不做公共索引。

作者拍板：模型 URL/preset 是否只服务作者自己的 workflow？

## Q4. 是否做 workflow 自动算依赖模型？

现状：`comfy-cli` 已提供 `deps-in-workflow --workflow`，但它偏节点依赖；模型引用静态解析容易被节点自定义字段破坏。

方向 A：短期只做 `model status --preset` 和 `model export-list`。
- 代价：不能从任意 workflow 自动恢复。
- 收益：准确、低风险。

方向 B：MVP 解析常见节点的 `widgets_values`，覆盖 Checkpoint/UNET/VAE/CLIP/LoRA。
- 代价：需要维护节点规则库。
- 收益：对作者常用 workflow 有明显帮助。

方向 C：深度接入 ComfyUI/Manager schema 或运行时 API。
- 代价：复杂且易跟版本耦合。
- 收益：长期更准。

倾向：B 作为 RFC，但必须限制为 "best-effort status"，不能自动下载。

作者拍板：首批只覆盖作者常用节点，还是完全不做？

## Q5. 是否抽象跨平台层？

现状：路径、权限、端口、网络都写死 AutoDL root Linux。

方向 A：继续 AutoDL-only。
- 代价：不能直接迁移 RunPod/Vast.ai。
- 收益：产品定位清晰，维护面小。

方向 B：抽象 `PlatformProfile`，先只实现 AutoDL。
- 代价：少量重构和测试成本。
- 收益：未来可验证 RunPod/Vast.ai，而不引入平台复杂度。

方向 C：全面跨平台。
- 代价：高，且偏离个人工具。
- 收益：潜在用户面扩大。

倾向：B 的轻量接口可以排期，但不要做 C。

作者拍板：是否把 RunPod/Vast.ai 作为 2026 年内目标？

## Q6. 是否提供 rclone / OSS / S3 集成？

现状：模型本体不进 Git，不自动下载；外部备份只在文档层提及。

方向 A：只写外部备份指南。
- 代价：用户要自己执行。
- 收益：零依赖，符合个人工具。

方向 B：提供 `model export-list` + 示例 `rclone` 脚本。
- 代价：需要文档和少量脚本维护。
- 收益：把大模型备份责任清晰交给用户。

方向 C：内置 rclone/S3 同步命令。
- 代价：凭据、错误恢复、带宽、费用、误删风险都会进入核心复杂度。
- 收益：模型恢复更完整。

倾向：B。C 暂时拒绝。

作者拍板：作者是否已有固定外部存储方案？

## Q7. 是否将代码 repo 发布为工具包，并把用户数据 repo 移出源码目录？

现状：`README.md` 要求 clone `autodl-instance` 到 `/root/autodl-tmp` 后运行；`init.sh`、`SystemAddon`、`UserdataAddon`、`status.py`、`models.config` 都默认 `my-comfyui-backup` 在代码仓目录下。

方向 A：维持当前混合仓库。
- 代价：工具升级、用户数据、sync 产物持续耦合，越往后越难迁移。
- 收益：当前一键脚本最简单，不需要 packaging。

方向 B：先拆路径，不马上发布。
- 代价：需要引入 `workspace_dir` / `userdata_dir`，改动多个路径 helper 和测试。
- 收益：低风险解除最大耦合，保留旧 `./init.sh` 体验。

方向 C：拆路径后做 Python package 发布。
- 代价：需要 `pyproject.toml`、console scripts、package data、release 验证和安装文档。
- 收益：最终用户只需要安装工具并维护自己的 `my-comfyui-backup` 数据 repo。

倾向：C，但分阶段执行：先 B，再 C。主入口收敛为 `autodl`，`start` / `bye` / `model` 保留兼容 shim。

作者拍板：
- 是否确认代码包发布是目标形态？
- package 名称用 `autodl-instance` 还是改成 `autodl-comfy`？
- 本地配置放 `/root/autodl-tmp/autodl-workspace/config.yaml` 还是 `~/.config/autodl-instance/config.yaml`？
- 数据 repo 是否记录期望工具版本并在不一致时 warning？

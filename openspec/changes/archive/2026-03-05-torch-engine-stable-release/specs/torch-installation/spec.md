## ADDED Requirements

### Requirement: PyTorch Stable Release Installation

系统 **MUST** 从 PyTorch 官方 stable 渠道安装 CUDA 版本的 PyTorch，而不是 nightly 预发布版本，以确保生产环境的稳定性。

#### Scenario: 首次安装 PyTorch

- **WHEN** 执行 `python -m src.main setup` 且 PyTorch 未安装或版本不满足要求
- **THEN** 系统 **SHALL** 从 `https://download.pytorch.org/whl/cu130` (stable) 下载安装 PyTorch
- **AND** 安装命令 **MUST NOT** 包含 `--pre` 参数
- **AND** 安装完成后 `torch.version.cuda` **SHALL** 返回 >= 13.0

#### Scenario: 幂等性检查通过

- **WHEN** 执行 `python -m src.main setup` 且已安装满足要求的 PyTorch
- **THEN** 系统 **SHALL** 跳过安装步骤
- **AND** 输出日志 "[SKIP] PyTorch (CUDA >= 13.0) 已就绪"

#### Scenario: 兼容 RTX PRO 6000 显卡

- **WHEN** 主机安装了 RTX PRO 6000 显卡 (Ada Lovelace 架构)
- **THEN** stable CUDA 13.0 版本 **SHALL** 完全兼容
- **AND** 所有 ComfyUI 工作流 **SHALL** 正常运行
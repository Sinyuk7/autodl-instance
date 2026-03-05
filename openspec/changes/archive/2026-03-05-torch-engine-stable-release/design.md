## Context

`torch_engine` 插件负责在 AutoDL 实例上安装和配置 PyTorch CUDA 环境。当前配置使用 nightly 预发布版本，需要切换到 stable 版本以提高生产环境稳定性。

## Goals / Non-Goals

**Goals:**
- 切换到 PyTorch stable release 渠道
- 保持现有的幂等性检查逻辑不变
- 保持与 RTX PRO 6000 (CUDA 13.0) 的兼容性

**Non-Goals:**
- 不修改驱动版本检查逻辑
- 不修改 CUDA 最低版本要求
- 不添加新功能或配置项

## Decisions

### Decision 1: 修改 manifest.yaml 中的 index_url

**变更:** `https://download.pytorch.org/whl/nightly/cu130` → `https://download.pytorch.org/whl/cu130`

**理由:** 根据 PyTorch 官方文档，stable 版本使用 `--extra-index-url` 而非 `--index-url`，但对于纯 CUDA 包，直接使用 `--index-url` 指向 stable wheel 仓库同样有效。

### Decision 2: 移除 --pre 安装参数

**变更:** 在 `plugin.py` 的 `_install_torch()` 方法中，从 uv 命令移除 `--pre` 参数。

**理由:** `--pre` 参数允许安装预发布版本，移除后 uv/pip 将只安装正式发布的稳定版本。

### Decision 3: 保持其他逻辑不变

幂等性检查 (`_is_torch_cuda_ready`) 和驱动版本校验 (`_check_driver_version`) 逻辑无需修改，它们与安装源无关。

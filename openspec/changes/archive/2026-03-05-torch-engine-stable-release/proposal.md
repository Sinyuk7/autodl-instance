## Why

当前 `torch_engine` 插件使用 PyTorch nightly 版本 (`cu130 nightly`)，在生产环境中可能存在稳定性风险。对于 AutoDL 云 GPU 实例（RTX PRO 6000），应该使用经过充分测试的稳定版本，以确保 ComfyUI 工作流的可靠运行。

## What Changes

- 将 PyTorch 安装源从 nightly 切换到 stable release
- 移除安装命令中的 `--pre` 预发布参数
- 保持 CUDA 13.0 版本兼容性不变

## Capabilities

### Modified Capabilities

- `torch-installation`: PyTorch 安装流程从 nightly 渠道切换到 stable 渠道

## Impact

- `src/addons/torch_engine/manifest.yaml`: 修改 `index_url` 指向 stable 源
- `src/addons/torch_engine/plugin.py`: 移除 `_install_torch()` 中的 `--pre` 参数

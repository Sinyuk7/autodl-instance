## 1. 修改配置文件

- [x] 1.1 修改 `src/addons/torch_engine/manifest.yaml` 中的 `index_url`，从 nightly 切换到 stable
  - 原值: `https://download.pytorch.org/whl/nightly/cu130`
  - 新值: `https://download.pytorch.org/whl/cu130`

## 2. 修改插件代码

- [x] 2.1 修改 `src/addons/torch_engine/plugin.py` 中的 `_install_torch()` 方法
  - 移除 `--pre` 参数，确保只安装正式发布版本
  - 同时更新了 `setup()` 中的默认 URL 值以保持一致性

## 3. 验证

- [x] 3.1 检查修改后的代码语法正确性
- [ ] 3.2 确认主流程 `python -m src.main setup` 可以正常执行（需要在 AutoDL 实例上验证）
# Addon 单元测试指南

## 测试原则

1. **只测公开方法**：`setup` / `start` / `sync`，私有方法通过公开方法间接覆盖
2. **核心场景优先**：Happy Path + 1-2 个最可能的异常场景
3. **验证结果而非过程**：关注状态变更和 artifacts，不验证命令细节

## 测试结构

```python
class TestSetup:
    def test_fresh_install_success(self, app_context, mock_runner):
        """全新安装成功"""
        addon = MyAddon()
        addon.setup(app_context)
        
        assert app_context.state.is_completed(StateKey.XXX)
        assert app_context.artifacts.xxx is not None

    def test_skip_when_already_installed(self, app_context, mock_runner):
        """已安装时跳过"""
        app_context.state.mark_completed(StateKey.XXX)
        
        addon = MyAddon()
        addon.setup(app_context)

class TestStart:
    def test_starts_successfully(self, app_context, mock_runner):
        """正常启动"""

class TestSync:
    def test_sync_completes(self, app_context):
        """sync 正常完成"""
```

## Fixture

- `app_context`: 完整的 AppContext（含 MockRunner、MockStateManager）
- `mock_runner`: 可用于检查命令调用
- `tmp_path`: pytest 提供的临时目录

## 注意事项

- 使用 `tmp_path` 避免污染真实文件系统
- 需要精确命令匹配时设置 `app_context.debug = False`
- Patch 路径使用插件模块路径：`patch("src.addons.xxx.plugin.func")`

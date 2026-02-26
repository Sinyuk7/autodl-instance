# 测试指南

## 测试简化原则

### 1. 只测公开接口

```python
# ❌ 避免：测试私有方法
def test_parse_version():
    assert _parse_version("1.2.3") == (1, 2, 3)

# ✅ 推荐：通过公开方法间接覆盖
def test_setup_validates_version():
    addon.setup(context)
    assert context.artifacts.xxx is not None
```

### 2. 核心场景优先

每个函数/方法只需覆盖：
- **1 个 Happy Path** - 正常执行成功
- **1-2 个关键异常** - 最可能出现的失败场景

```python
# ❌ 避免：为每个参数值写独立测试
def test_until_system(): ...
def test_until_git_config(): ...
def test_until_torch_engine(): ...
def test_until_comfy_core(): ...
def test_until_userdata(): ...

# ✅ 推荐：一个测试覆盖参数传递逻辑
def test_until_parameter_passed_to_execute():
    monkeypatch.setattr("sys.argv", ["main.py", "setup", "--until", "comfy_core"])
    main()
    assert execute_mock.call_args[1]["until"] == "comfy_core"
```

### 3. 验证结果而非过程

```python
# ❌ 避免：验证命令细节
assert "curl -sSL https://..." in mock_runner.calls[0].cmd

# ✅ 推荐：验证最终状态
assert context.artifacts.uv_bin.exists()
```

### 4. 合并相似测试

使用 `@pytest.mark.parametrize` 合并同类测试：

```python
# ❌ 避免
def test_setup_action(): ...
def test_start_action(): ...
def test_sync_action(): ...

# ✅ 推荐
@pytest.mark.parametrize("action", ["setup", "start", "sync"])
def test_valid_actions(action, mock_dependencies, monkeypatch):
    monkeypatch.setattr("sys.argv", ["main.py", action])
    main()
    assert mock_dependencies["execute"].call_args[0][0] == action
```

---

## 测试分类与优先级

| 优先级 | 定义 | 示例 | 删减建议 |
|--------|------|------|----------|
| **P0 必须** | 核心流程、关键边界 | Happy Path、致命错误处理 | 不可删 |
| **P1 重要** | 主要分支、配置验证 | 参数传递、状态检查 | 保留 1 个代表 |
| **P2 可选** | 冗余覆盖、实现细节 | 多个相似参数测试 | 可合并或删除 |

### 判断标准

问自己：**"如果这个测试被删除，会漏掉什么 bug？"**

- 答不上来 → P2，可删
- 能答上来但场景罕见 → P1，考虑合并
- 能答上来且是常见场景 → P0，保留

---

## test_main.py 重构建议

当前 `test_main.py` 有 473 行，可精简至 ~200 行。

### TestLoadManifests（当前 8 个 → 建议 4 个）

| 测试 | 优先级 | 建议 |
|------|--------|------|
| `test_loads_addon_manifests` | P0 | ✅ 保留 |
| `test_loads_lib_manifests` | P2 | ❌ 合并到上一个 |
| `test_returns_dict_with_module_name_as_key` | P2 | ❌ 删除（被 P0 覆盖） |
| `test_torch_engine_manifest_content` | P2 | ❌ 删除（测试真实文件内容不稳定） |
| `test_download_manifest_content` | P2 | ❌ 删除（同上） |
| `test_missing_directory_handled` | P0 | ✅ 保留 |
| `test_empty_manifest_returns_empty_dict` | P1 | ✅ 保留 |
| `test_skips_non_directory_entries` | P2 | ❌ 合并 |
| `test_skips_directories_without_manifest` | P2 | ❌ 合并到上一个 |

### TestCreateContext（当前 9 个 → 建议 3 个）

| 测试 | 优先级 | 建议 |
|------|--------|------|
| `test_returns_app_context` | P0 | ✅ 保留 |
| `test_project_root_is_correct` | P2 | ❌ 合并到 P0 |
| `test_base_dir_is_correct` | P2 | ❌ 合并到 P0 |
| `test_debug_flag_default_false` | P1 | ✅ 保留（合并 true/false） |
| `test_debug_flag_propagates_true` | P2 | ❌ 合并到上一个 |
| `test_has_subprocess_runner` | P2 | ❌ 删除 |
| `test_file_state_manager_called_with_base_dir` | P2 | ❌ 删除 |
| `test_manifests_are_loaded` | P1 | ✅ 保留 |
| `test_artifacts_initialized` | P2 | ❌ 删除 |
| `test_execution_log_initialized_empty` | P2 | ❌ 删除 |

### TestMain（当前 16 个 → 建议 5 个）

| 测试 | 优先级 | 建议 |
|------|--------|------|
| `test_setup/start/sync_action` (3个) | P1 | ⚡ 合并为 1 个 parametrize |
| `test_invalid_action_rejected` | P0 | ✅ 保留 |
| `test_debug_flag_*` (2个) | P1 | ⚡ 合并为 1 个 |
| `test_until_*` (3个) | P1 | ⚡ 合并为 1 个 |
| `test_only_*` (2个) | P1 | ⚡ 合并为 1 个 |
| `test_combined_*` (2个) | P2 | ❌ 删除（被上面覆盖） |
| `test_setup_logger_called` | P2 | ❌ 删除 |
| `test_kill_process_called` | P2 | ❌ 删除 |
| `test_setup_network_called` | P2 | ❌ 删除 |
| `test_execution_order` | P1 | ✅ 保留（唯一验证顺序的） |

### 重构后示例

```python
class TestMain:
    """main() CLI 入口测试 - 精简版"""

    @pytest.mark.parametrize("action", ["setup", "start", "sync"])
    def test_valid_actions(self, mock_dependencies, monkeypatch, action):
        """有效 action 正确传递"""
        monkeypatch.setattr("sys.argv", ["main.py", action])
        main()
        assert mock_dependencies["execute"].call_args[0][0] == action

    def test_invalid_action_rejected(self, mock_dependencies, monkeypatch):
        """无效 action 被拒绝"""
        monkeypatch.setattr("sys.argv", ["main.py", "invalid"])
        with pytest.raises(SystemExit):
            main()

    @pytest.mark.parametrize("flag,expected", [("", False), ("--debug", True)])
    def test_debug_flag(self, mock_dependencies, monkeypatch, flag, expected):
        """--debug 参数传递"""
        args = ["main.py", "setup"] + ([flag] if flag else [])
        monkeypatch.setattr("sys.argv", args)
        main()
        assert mock_dependencies["create_context"].call_args[1]["debug"] == expected

    def test_until_and_only_params(self, mock_dependencies, monkeypatch):
        """--until/--only 参数传递"""
        monkeypatch.setattr("sys.argv", ["main.py", "setup", "--until", "system"])
        main()
        assert mock_dependencies["execute"].call_args[1]["until"] == "system"

    def test_execution_order(self, mock_dependencies, monkeypatch):
        """初始化顺序正确"""
        # ... 保持原有逻辑
```

---

## 目录结构

```
tests/
├── README.md           # 本文件
├── conftest.py         # 共享 fixtures
├── mocks.py            # Mock 实现
├── unit/               # 单元测试
│   ├── addons/         # Addon 测试（参考 addons/README.md）
│   ├── download/       # 下载模块测试
│   ├── test_main.py    # 主入口测试
│   └── test_pipeline.py
└── integration/        # 集成测试（参考 integration/README.md）
```

## 运行测试

```bash
# 全部测试
pytest tests/ -v

# 只跑单元测试
pytest tests/unit/ -v

# 跑特定文件
pytest tests/unit/test_main.py -v

# 带覆盖率
pytest tests/ --cov=src --cov-report=html
```

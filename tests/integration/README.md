# Integration Tests

集成测试目录，测试 `execute()` 函数的完整执行流程。

## 目录结构

```
tests/integration/
├── conftest.py              # 共享 fixtures（context_with_home, integration_runner）
├── README.md                # 本文件
├── test_setup_pipeline.py   # setup action 测试
├── test_start_pipeline.py   # start action 测试
├── test_sync_pipeline.py    # sync action 测试
└── test_e2e_scenarios.py    # 端到端场景测试
```

## 测试策略

### 核心设计

1. **使用 MockRunner**：拦截所有 shell 命令，不实际执行外部程序
2. **真实 Python 逻辑**：Addon 的 Python 代码正常执行，只是不调用真实 shell
3. **验证 Artifacts**：检查 `context.artifacts` 的状态变化
4. **隔离环境**：使用临时目录模拟 `$HOME`，不影响本地环境

### Fixtures 说明

- `fake_home` - 临时目录作为假的 HOME
- `integration_runner` - MockRunner 实例，记录所有命令
- `context_with_home` - 完整配置的 AppContext

## 测试用例概览

### test_setup_pipeline.py（预估 15-20 个）

| 类名 | 状态 | 描述 |
|-----|------|-----|
| TestSetupUntilSystem | ✅ 已实现 | `--until system` 场景 |
| TestSetupUntilGitConfig | ✅ 已实现 | `--until git_config` 场景 |
| TestSetupUntilTorchEngine | ✅ 已实现 | `--until torch_engine` 场景 |
| TestSetupUntilComfyCore | ✅ 已实现 | `--until comfy_core` 场景 |
| TestSetupUntilUserdata | 📋 TODO | `--until userdata` 场景 |
| TestSetupUntilNodes | 📋 TODO | `--until nodes` 场景 |
| TestSetupUntilModels | 📋 TODO | `--until models` 场景 |
| TestSetupOnlyMode | ✅ 已实现 | `--only` 模式 |
| TestSetupFullPipeline | ✅ 已实现 | 完整流程测试 |
| TestSetupCommandExecution | ✅ 已实现 | 命令执行验证 |
| TestSetupIdempotency | ✅ 已实现 | 幂等性测试 |
| TestSetupEdgeCases | 📋 TODO | 边界情况 |

### test_start_pipeline.py（预估 5-10 个）

| 类名 | 状态 | 描述 |
|-----|------|-----|
| TestStartWithSetupComplete | 📋 TODO | setup 后启动 |
| TestStartCommandGeneration | 📋 TODO | 启动命令生成 |
| TestStartComfyUI | 📋 TODO | ComfyUI 进程启动 |
| TestStartOnlyMode | 📋 TODO | `--only` 模式 |
| TestStartErrorHandling | 📋 TODO | 错误处理 |

### test_sync_pipeline.py（预估 5-10 个）

| 类名 | 状态 | 描述 |
|-----|------|-----|
| TestSyncReverseOrder | 📋 TODO | 逆序执行验证 |
| TestSyncUserdata | 📋 TODO | 用户数据同步 |
| TestSyncWorkflows | 📋 TODO | 工作流同步 |
| TestSyncNodes | 📋 TODO | 节点状态同步 |
| TestSyncModels | 📋 TODO | 模型同步 |
| TestSyncWithRemote | 📋 TODO | 远程同步 |

### test_e2e_scenarios.py（预估 15-20 个）

| 类名 | 状态 | 描述 |
|-----|------|-----|
| TestFullLifecycle | 📋 TODO | 完整生命周期 |
| TestResumeFromFailure | 📋 TODO | 故障恢复 |
| TestEnvironmentVariation | 📋 TODO | 环境变化 |
| TestConfigurationVariation | 📋 TODO | 配置变化 |
| TestErrorHandling | 📋 TODO | 错误处理 |
| TestPluginInteraction | 📋 TODO | 插件交互 |

## 运行测试

```bash
# 运行所有集成测试
pytest tests/integration/ -v

# 运行特定文件
pytest tests/integration/test_setup_pipeline.py -v

# 运行特定测试类
pytest tests/integration/test_setup_pipeline.py::TestSetupUntilSystem -v

# 带覆盖率
pytest tests/integration/ --cov=src --cov-report=html
```

## 添加新测试

1. 使用 `context_with_home` fixture 获取配置好的 context
2. 使用 `integration_runner` fixture 获取 MockRunner（如需验证命令）
3. 调用 `execute(action, context, **options)`
4. 断言 `context.artifacts` 的状态

```python
def test_example(self, context_with_home: AppContext):
    """示例测试"""
    execute("setup", context_with_home, until="system")
    
    assert context_with_home.artifacts.uv_bin is not None
```

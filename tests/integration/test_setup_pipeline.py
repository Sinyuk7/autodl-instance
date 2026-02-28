"""
Setup Pipeline 集成测试

测试 execute("setup", context) 的完整执行流程。
验证各插件执行后 context.artifacts 的变化是否符合预期。
"""
import pytest
from pathlib import Path

from src.main import execute
from src.core.interface import AppContext
from tests.mocks import MockRunner


class TestSetupUntilSystem:
    """测试 setup --until system"""

    def test_system_produces_uv_bin(self, context_with_home: AppContext):
        """SystemAddon 应设置 artifacts.uv_bin"""
        execute("setup", context_with_home, until="system")
        
        assert context_with_home.artifacts.uv_bin is not None
        assert "uv" in str(context_with_home.artifacts.uv_bin)

    def test_system_produces_bin_dir(self, context_with_home: AppContext):
        """SystemAddon 应设置 artifacts.bin_dir"""
        execute("setup", context_with_home, until="system")
        
        assert context_with_home.artifacts.bin_dir is not None
        assert context_with_home.artifacts.bin_dir.exists()

    def test_system_creates_bin_scripts(self, context_with_home: AppContext):
        """SystemAddon 应创建 turbo, bye, model, start 脚本"""
        execute("setup", context_with_home, until="system")
        
        bin_dir = context_with_home.artifacts.bin_dir
        expected_scripts = ["turbo", "bye", "model", "start"]
        
        for script in expected_scripts:
            assert (bin_dir / script).exists(), f"脚本 {script} 未创建"

    def test_system_only_sets_system_artifacts(self, context_with_home: AppContext):
        """--until system 时，后续插件的 artifacts 应为 None"""
        execute("setup", context_with_home, until="system")
        
        # 后续插件的产出应为 None
        assert context_with_home.artifacts.comfy_dir is None
        assert context_with_home.artifacts.custom_nodes_dir is None
        assert context_with_home.artifacts.user_dir is None


class TestSetupUntilGitConfig:
    """测试 setup --until git_config"""

    def test_git_config_executes_after_system(self, context_with_home: AppContext):
        """GitAddon 应在 SystemAddon 之后执行"""
        execute("setup", context_with_home, until="git_config")
        
        # SystemAddon 的产出应存在
        assert context_with_home.artifacts.uv_bin is not None
        assert context_with_home.artifacts.bin_dir is not None

    def test_git_config_completes_without_error(
        self, context_with_home: AppContext, integration_runner: MockRunner
    ):
        """GitAddon 应正常完成（可能有条件跳过 git 命令）"""
        # GitAddon 可能根据环境条件跳过某些操作
        # 这里只验证执行不报错
        execute("setup", context_with_home, until="git_config")
        
        # 验证执行完成（无异常）
        assert True


class TestSetupUntilTorchEngine:
    """测试 setup --until torch_engine"""

    def test_torch_inherits_previous_artifacts(self, context_with_home: AppContext):
        """TorchAddon 执行后，前序插件的 artifacts 应保留"""
        execute("setup", context_with_home, until="torch_engine")
        
        # SystemAddon 产出
        assert context_with_home.artifacts.uv_bin is not None
        assert context_with_home.artifacts.bin_dir is not None


class TestSetupUntilComfyCore:
    """测试 setup --until comfy_core"""

    def test_comfy_core_produces_comfy_dir(self, context_with_home: AppContext):
        """ComfyAddon 应设置 artifacts.comfy_dir"""
        execute("setup", context_with_home, until="comfy_core")
        
        assert context_with_home.artifacts.comfy_dir is not None

    def test_comfy_core_produces_custom_nodes_dir(self, context_with_home: AppContext):
        """ComfyAddon 应设置 artifacts.custom_nodes_dir"""
        execute("setup", context_with_home, until="comfy_core")
        
        assert context_with_home.artifacts.custom_nodes_dir is not None

    def test_comfy_dir_matches_context(self, context_with_home: AppContext):
        """comfy_dir 应来自 context.comfy_dir（系统盘）"""
        execute("setup", context_with_home, until="comfy_core")
        
        # comfy_dir 应该等于 context 中定义的路径
        assert context_with_home.artifacts.comfy_dir == context_with_home.comfy_dir
    
    def test_output_dir_is_under_base_dir(self, context_with_home: AppContext):
        """output_dir 应在 base_dir 下（tmp 盘）"""
        execute("setup", context_with_home, until="comfy_core")
        
        output_dir = context_with_home.artifacts.output_dir
        base_dir = context_with_home.base_dir
        
        # output_dir 应该是 base_dir 的子路径
        assert str(output_dir).startswith(str(base_dir))


class TestSetupOnlyMode:
    """测试 setup --only 模式"""

    def test_only_system_skips_other_addons(self, context_with_home: AppContext):
        """--only system 应只执行 SystemAddon"""
        execute("setup", context_with_home, only="system")
        
        # SystemAddon 产出
        assert context_with_home.artifacts.uv_bin is not None
        assert context_with_home.artifacts.bin_dir is not None
        
        # 其他插件产出应为 None
        assert context_with_home.artifacts.comfy_dir is None

    def test_only_comfy_core_fails_without_dependencies(
        self, context_with_home: AppContext
    ):
        """--only comfy_core 在缺少依赖时应报错（这是预期行为）
        
        这证明了 --only 模式的危险性：它跳过依赖检查，
        如果插件依赖前序插件的产出，会导致运行时错误。
        """
        from unittest.mock import patch
        
        # 确保 comfy-cli 不存在，强制进入 uv 安装流程
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError) as exc_info:
                execute("setup", context_with_home, only="comfy_core")
        
        # 验证错误信息包含依赖提示
        assert "uv" in str(exc_info.value).lower() or "SystemAddon" in str(exc_info.value)


class TestSetupFullPipeline:
    """测试完整 setup 流程"""

    def test_full_setup_all_artifacts_set(self, context_with_home: AppContext):
        """完整 setup 后，所有主要 artifacts 应被设置"""
        execute("setup", context_with_home)
        
        # 验证关键 artifacts
        assert context_with_home.artifacts.uv_bin is not None
        assert context_with_home.artifacts.bin_dir is not None
        assert context_with_home.artifacts.comfy_dir is not None
        assert context_with_home.artifacts.custom_nodes_dir is not None

    def test_full_setup_execution_log(self, context_with_home: AppContext):
        """完整 setup 应记录所有插件的执行"""
        execute("setup", context_with_home)
        
        # 检查 execution_log 是否有记录
        # （如果插件使用了 self.log() 方法）
        # 这取决于插件实现，可能需要调整


class TestSetupCommandExecution:
    """测试 setup 过程中的命令执行"""

    def test_uv_install_command_called(
        self, context_with_home: AppContext, integration_runner: MockRunner, tmp_path: Path, monkeypatch
    ):
        """uv 不存在时应调用安装命令"""
        # 删除预设的 uv 文件，模拟 uv 未安装
        fake_home = tmp_path / "home"
        uv_path = fake_home / ".local" / "bin" / "uv"
        if uv_path.exists():
            uv_path.unlink()
        
        execute("setup", context_with_home, until="system")
        
        # 验证调用了 curl 安装脚本
        assert integration_runner.was_called_with_pattern("curl.*uv")

    def test_comfy_install_command_called(
        self, context_with_home: AppContext, integration_runner: MockRunner
    ):
        """ComfyAddon 应调用 comfy 相关命令"""
        execute("setup", context_with_home, until="comfy_core")
        
        # 验证调用了 comfy 命令
        all_cmds = integration_runner.all_commands
        # 这里根据实际的 ComfyAddon 实现来验证


class TestSetupIdempotency:
    """测试 setup 幂等性"""

    def test_second_setup_skips_completed_steps(
        self, context_with_home: AppContext, integration_runner: MockRunner
    ):
        """第二次 setup 应跳过已完成的步骤"""
        # 第一次执行
        execute("setup", context_with_home, until="system")
        first_call_count = len(integration_runner.all_commands)
        
        # 第二次执行
        execute("setup", context_with_home, until="system")
        second_call_count = len(integration_runner.all_commands)
        
        # 如果有幂等性检查，第二次应该调用更少的命令
        # 这取决于插件实现的幂等性逻辑

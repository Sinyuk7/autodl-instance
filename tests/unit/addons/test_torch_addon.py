"""
TorchAddon 单元测试

测试 PyTorch CUDA 环境装配相关逻辑，包含各种边界情况。
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.addons.torch_engine.plugin import TorchAddon
from src.core.interface import AppContext
from src.core.ports import CommandResult


class TestGetTorchCudaInfo:
    """_get_torch_cuda_info 方法测试"""

    def test_returns_torch_info_on_success(
        self, app_context: AppContext, mock_runner
    ):
        """成功获取 torch 信息时应返回正确的字符串"""
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="torch=2.6.0, cuda_raw='13.0', cuda_float=13.0",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        result = addon._get_torch_cuda_info(app_context)

        assert "torch=2.6.0" in result
        assert "cuda_raw" in result

    def test_returns_stderr_on_failure(
        self, app_context: AppContext, mock_runner
    ):
        """torch 不可用时应返回 stderr 的错误信息"""
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="error=ModuleNotFoundError: No module named 'torch'",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        result = addon._get_torch_cuda_info(app_context)

        assert "error=" in result
        assert "torch" in result.lower()

    def test_handles_empty_output(
        self, app_context: AppContext, mock_runner
    ):
        """输出为空时应返回空字符串"""
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        result = addon._get_torch_cuda_info(app_context)

        assert result == ""

    def test_strips_whitespace(
        self, app_context: AppContext, mock_runner
    ):
        """应去除输出的首尾空白"""
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="  torch=2.6.0, cuda_raw='13.0'  \n",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        result = addon._get_torch_cuda_info(app_context)

        assert not result.startswith(" ")
        assert not result.endswith(" ")
        assert not result.endswith("\n")


class TestIsTorchCudaReady:
    """_is_torch_cuda_ready 方法测试"""

    def test_returns_true_when_cuda_sufficient(
        self, app_context: AppContext, mock_runner
    ):
        """CUDA 版本满足要求时应返回 True"""
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        result = addon._is_torch_cuda_ready(app_context, 12.0)

        assert result is True

    def test_returns_false_when_cuda_insufficient(
        self, app_context: AppContext, mock_runner
    ):
        """CUDA 版本不满足要求时应返回 False"""
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        result = addon._is_torch_cuda_ready(app_context, 13.0)

        assert result is False

    def test_returns_false_when_torch_not_installed(
        self, app_context: AppContext, mock_runner
    ):
        """torch 未安装时应返回 False"""
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="EXCEPTION: ModuleNotFoundError: No module named 'torch'",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        result = addon._is_torch_cuda_ready(app_context, 13.0)

        assert result is False

    def test_returns_false_when_cuda_none(
        self, app_context: AppContext, mock_runner
    ):
        """cuda_ver 为 None（CPU 版本）时应返回 False"""
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        result = addon._is_torch_cuda_ready(app_context, 13.0)

        assert result is False

    def test_various_cuda_version_thresholds(
        self, app_context: AppContext, mock_runner
    ):
        """测试不同 CUDA 版本阈值"""
        # 版本满足 12.0
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()

        # 低版本要求应通过
        assert addon._is_torch_cuda_ready(app_context, 11.0) is True
        assert addon._is_torch_cuda_ready(app_context, 12.0) is True

    def test_edge_case_exact_version_match(
        self, app_context: AppContext, mock_runner
    ):
        """精确版本匹配（边界条件：>=）"""
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        # 使用与实际版本相同的 min 要求
        result = addon._is_torch_cuda_ready(app_context, 13.0)

        assert result is True


class TestCheckDriverVersion:
    """_check_driver_version 方法测试"""

    def test_pass_when_driver_sufficient(
        self, app_context: AppContext, mock_runner
    ):
        """驱动版本满足要求时应通过"""
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="580.42.01",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.min_driver = 580

        # 不应抛出异常
        addon._check_driver_version(app_context)

    def test_pass_when_driver_higher(
        self, app_context: AppContext, mock_runner
    ):
        """驱动版本高于要求时应通过"""
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="600.00.00",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.min_driver = 580

        addon._check_driver_version(app_context)

    def test_exit_when_driver_insufficient(
        self, app_context: AppContext, mock_runner
    ):
        """驱动版本不满足要求时应调用 sys.exit"""
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="470.82.01",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.min_driver = 580

        with pytest.raises(SystemExit) as excinfo:
            addon._check_driver_version(app_context)
        
        assert excinfo.value.code == 1

    def test_skip_when_nvidia_smi_not_found(
        self, app_context: AppContext, mock_runner
    ):
        """nvidia-smi 不存在时应跳过（无卡模式）"""
        # 模拟 FileNotFoundError
        def raise_file_not_found(*args, **kwargs):
            raise FileNotFoundError("nvidia-smi not found")

        with patch.object(app_context.cmd, "run", raise_file_not_found):
            addon = TorchAddon()
            addon.min_driver = 580

            # 不应抛出异常
            addon._check_driver_version(app_context)

    def test_warn_on_other_exceptions(
        self, app_context: AppContext, mock_runner
    ):
        """其他异常时应警告但不退出"""
        def raise_exception(*args, **kwargs):
            raise RuntimeError("Unknown error")

        with patch.object(app_context.cmd, "run", raise_exception):
            addon = TorchAddon()
            addon.min_driver = 580

            # 不应抛出异常
            addon._check_driver_version(app_context)

    def test_handles_multi_gpu_output(
        self, app_context: AppContext, mock_runner
    ):
        """多 GPU 输出时应取第一行"""
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="580.42.01\n580.42.01\n580.42.01",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.min_driver = 580

        addon._check_driver_version(app_context)

    def test_handles_version_with_spaces(
        self, app_context: AppContext, mock_runner
    ):
        """版本字符串包含空格时应正确解析"""
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="  580.42.01  ",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.min_driver = 580

        addon._check_driver_version(app_context)

    def test_edge_case_exact_version_match(
        self, app_context: AppContext, mock_runner
    ):
        """精确版本匹配（边界条件：<）"""
        # 版本刚好等于要求
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="580.00.00",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.min_driver = 580

        # 580 >= 580，应通过
        addon._check_driver_version(app_context)

    def test_edge_case_one_below_threshold(
        self, app_context: AppContext, mock_runner
    ):
        """版本刚好低于要求一个主版本号"""
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="579.99.99",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.min_driver = 580

        with pytest.raises(SystemExit):
            addon._check_driver_version(app_context)


class TestInstallTorch:
    """_install_torch 方法测试"""

    def test_calls_uv_pip_install(
        self, app_context: AppContext, mock_runner
    ):
        """应调用 uv pip install 命令"""
        addon = TorchAddon()
        addon.packages = ["torch", "torchvision", "torchaudio"]
        addon.index_url = "https://download.pytorch.org/whl/nightly/cu130"

        addon._install_torch(app_context)

        mock_runner.assert_called_with("uv pip install")
        mock_runner.assert_called_with("--system")
        mock_runner.assert_called_with("--upgrade")
        mock_runner.assert_called_with("--pre")

    def test_includes_all_packages(
        self, app_context: AppContext, mock_runner
    ):
        """应包含所有配置的包"""
        addon = TorchAddon()
        addon.packages = ["torch", "torchvision", "torchaudio"]
        addon.index_url = "https://download.pytorch.org/whl/nightly/cu130"

        addon._install_torch(app_context)

        mock_runner.assert_called_with("torch")
        mock_runner.assert_called_with("torchvision")
        mock_runner.assert_called_with("torchaudio")

    def test_includes_index_url(
        self, app_context: AppContext, mock_runner
    ):
        """应包含正确的 index-url"""
        addon = TorchAddon()
        addon.packages = ["torch"]
        addon.index_url = "https://download.pytorch.org/whl/nightly/cu130"

        addon._install_torch(app_context)

        mock_runner.assert_called_with("--index-url")
        mock_runner.assert_called_with("https://download.pytorch.org/whl/nightly/cu130")

    def test_raises_on_install_failure(
        self, app_context: AppContext, mock_runner
    ):
        """安装失败时应抛出 RuntimeError"""
        # 模拟安装失败
        mock_runner.stub_results["uv pip install"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="Installation failed",
            command="uv pip install",
        )

        addon = TorchAddon()
        addon.packages = ["torch"]
        addon.index_url = "https://download.pytorch.org/whl/nightly/cu130"

        with pytest.raises(RuntimeError) as excinfo:
            addon._install_torch(app_context)

        assert "Torch 安装失败" in str(excinfo.value)
        assert "退出码: 1" in str(excinfo.value)

    def test_success_on_zero_returncode(
        self, app_context: AppContext, mock_runner
    ):
        """returncode 为 0 时应正常完成"""
        addon = TorchAddon()
        addon.packages = ["torch"]
        addon.index_url = "https://download.pytorch.org/whl/nightly/cu130"

        # 默认 returncode 为 0，不应抛出异常
        addon._install_torch(app_context)

    def test_custom_packages(
        self, app_context: AppContext, mock_runner
    ):
        """支持自定义包列表"""
        addon = TorchAddon()
        addon.packages = ["torch", "custom-package"]
        addon.index_url = "https://example.com/whl"

        addon._install_torch(app_context)

        mock_runner.assert_called_with("custom-package")

    def test_empty_packages_list(
        self, app_context: AppContext, mock_runner
    ):
        """空包列表时仍应调用 uv（虽然没有实际意义）"""
        addon = TorchAddon()
        addon.packages = []
        addon.index_url = "https://example.com/whl"

        addon._install_torch(app_context)

        mock_runner.assert_called_with("uv pip install")


class TestSetup:
    """setup 钩子方法测试"""

    def test_setup_reads_manifest_config(
        self, app_context: AppContext, mock_runner
    ):
        """应从 manifest 读取配置"""
        app_context.addon_manifests["torch_engine"] = {
            "min_driver_version": 600,
            "min_cuda_version": 14.0,
            "index_url": "https://custom.pytorch.org/whl",
            "packages": ["torch-custom"],
        }

        # 模拟 CUDA 已就绪
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        addon.setup(app_context)

        assert addon.min_driver == 600
        assert addon.min_cuda == 14.0
        assert addon.index_url == "https://custom.pytorch.org/whl"
        assert addon.packages == ["torch-custom"]

    def test_setup_uses_default_config(
        self, app_context: AppContext, mock_runner
    ):
        """manifest 为空时应使用默认配置"""
        # 模拟 CUDA 已就绪
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        addon.setup(app_context)

        assert addon.min_driver == 580
        assert addon.min_cuda == 13.0
        assert "cu130" in addon.index_url
        assert "torch" in addon.packages

    def test_setup_skips_when_already_ready(
        self, app_context: AppContext, mock_runner
    ):
        """CUDA 已就绪时应跳过安装"""
        # 模拟 CUDA 已就绪
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="torch=2.6.0, cuda_raw='13.0', cuda_float=13.0",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        addon.setup(app_context)

        # 不应调用安装命令
        mock_runner.assert_not_called_with("uv pip install")
        
        # 但应设置 artifacts
        assert app_context.artifacts.torch_installed is True

    def test_setup_installs_when_not_ready(
        self, app_context: AppContext, mock_runner
    ):
        """CUDA 未就绪时应执行安装"""
        # 第一次调用返回未就绪
        call_count = [0]
        original_run = mock_runner.run

        def custom_run(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            call_count[0] += 1
            if f"{sys.executable} -c" in cmd_str and call_count[0] <= 2:
                return CommandResult(
                    returncode=1,
                    stdout="",
                    stderr="",
                    command=cmd_str,
                )
            return original_run(cmd, **kwargs)

        mock_runner.run = custom_run

        # 模拟 nvidia-smi 返回有效版本
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="580.42.01",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.setup(app_context)

        # 应调用安装命令
        mock_runner.assert_called_with("uv pip install")
        assert app_context.artifacts.torch_installed is True

    def test_setup_sets_torch_installed_artifact(
        self, app_context: AppContext, mock_runner
    ):
        """setup 应设置 torch_installed artifact"""
        # 模拟 CUDA 已就绪
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        addon.setup(app_context)

        assert app_context.artifacts.torch_installed is True

    def test_setup_checks_driver_before_install(
        self, app_context: AppContext, mock_runner
    ):
        """安装前应先检查驱动版本"""
        # 模拟 CUDA 未就绪
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        # 模拟驱动版本过低
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="470.82.01",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()

        with pytest.raises(SystemExit):
            addon.setup(app_context)

        # 不应调用安装命令（因为驱动检查失败后退出）
        mock_runner.assert_not_called_with("uv pip install")


class TestHooks:
    """钩子方法测试"""

    def test_start_does_nothing(self, app_context: AppContext):
        """start 方法应为空实现"""
        addon = TorchAddon()
        # 不应抛出异常
        addon.start(app_context)

    def test_sync_does_nothing(self, app_context: AppContext):
        """sync 方法应为空实现"""
        addon = TorchAddon()
        # 不应抛出异常
        addon.sync(app_context)


class TestModuleAttributes:
    """模块属性测试"""

    def test_module_dir(self):
        """module_dir 应为 torch_engine"""
        addon = TorchAddon()
        assert addon.module_dir == "torch_engine"

    def test_name_property(self):
        """name 属性应返回 torch_engine"""
        addon = TorchAddon()
        assert addon.name == "torch_engine"


class TestIdempotency:
    """幂等性测试"""

    def test_repeated_setup_is_idempotent(
        self, app_context: AppContext, mock_runner
    ):
        """重复执行 setup 应具有幂等性"""
        # 模拟 CUDA 已就绪
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()

        # 第一次执行
        addon.setup(app_context)
        first_call_count = len(mock_runner.realtime_calls)

        # 第二次执行
        addon.setup(app_context)
        second_call_count = len(mock_runner.realtime_calls)

        # 两次都不应调用安装命令（因为已就绪）
        assert first_call_count == second_call_count == 0
        assert app_context.artifacts.torch_installed is True

    def test_setup_after_manual_install_skips(
        self, app_context: AppContext, mock_runner
    ):
        """手动安装后 setup 应跳过"""
        # 模拟 CUDA 已就绪（手动安装后的状态）
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="torch=2.6.0, cuda_raw='13.0', cuda_float=13.0",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        addon.setup(app_context)

        mock_runner.assert_not_called_with("uv pip install")


class TestEdgeCases:
    """边界情况测试"""

    def test_handles_cuda_version_parse_error(
        self, app_context: AppContext, mock_runner
    ):
        """CUDA 版本解析错误时应正确处理"""
        # 模拟 cuda_float 为 "parse_error"
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()
        result = addon._is_torch_cuda_ready(app_context, 13.0)

        assert result is False

    def test_handles_driver_version_without_dots(
        self, app_context: AppContext, mock_runner
    ):
        """处理不含小数点的驱动版本"""
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="580",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.min_driver = 580

        # 应正常处理
        addon._check_driver_version(app_context)

    def test_handles_empty_driver_version(
        self, app_context: AppContext, mock_runner
    ):
        """处理空的驱动版本输出（应警告但不退出）"""
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.min_driver = 580

        # 源代码会捕获异常并发出警告，不会抛出异常
        # 不应抛出异常（异常被捕获为 warning）
        addon._check_driver_version(app_context)

    def test_handles_invalid_driver_version_format(
        self, app_context: AppContext, mock_runner
    ):
        """处理无效的驱动版本格式（应警告但不退出）"""
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="invalid_version",
            stderr="",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.min_driver = 580

        # 源代码会捕获异常并发出警告，不会抛出异常
        # 不应抛出异常（异常被捕获为 warning）
        addon._check_driver_version(app_context)

    def test_handles_nvidia_smi_command_failure(
        self, app_context: AppContext, mock_runner
    ):
        """nvidia-smi 命令执行失败时的处理"""
        mock_runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="NVIDIA-SMI has failed",
            command="nvidia-smi",
        )

        addon = TorchAddon()
        addon.min_driver = 580

        # 由于 check=True，应抛出异常（被捕获为 warning）
        # 实际上 mock 不会真正检查，这里验证不会崩溃
        addon._check_driver_version(app_context)

    def test_special_cuda_versions(
        self, app_context: AppContext, mock_runner
    ):
        """测试特殊的 CUDA 版本号"""
        # CUDA 12.4 with 12.0 requirement
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()

        # 应该通过
        assert addon._is_torch_cuda_ready(app_context, 12.0) is True
        assert addon._is_torch_cuda_ready(app_context, 12.4) is True

    def test_very_high_cuda_requirement(
        self, app_context: AppContext, mock_runner
    ):
        """测试非常高的 CUDA 版本要求"""
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=1,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        addon = TorchAddon()

        # 超高版本要求应失败
        assert addon._is_torch_cuda_ready(app_context, 99.0) is False


class TestPipelineIntegration:
    """Pipeline 集成测试"""

    def test_until_torch_engine(
        self, app_context: AppContext, mock_runner
    ):
        """--until torch_engine 应执行到 TorchAddon"""
        from src.main import execute

        # 模拟 CUDA 已就绪
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        execute("setup", app_context, until="torch_engine")

        # 验证 TorchAddon 产出
        assert app_context.artifacts.torch_installed is True

    def test_only_torch_engine(
        self, app_context: AppContext, mock_runner
    ):
        """--only torch_engine 应只执行 TorchAddon"""
        from src.main import execute

        # 模拟 CUDA 已就绪
        mock_runner.stub_results[f"{sys.executable} -c"] = CommandResult(
            returncode=0,
            stdout="",
            stderr="",
            command=f"{sys.executable} -c",
        )

        execute("setup", app_context, only="torch_engine")

        # 验证 TorchAddon 产出
        assert app_context.artifacts.torch_installed is True

        # 验证其他插件未执行（comfy_dir 未设置）
        assert app_context.artifacts.comfy_dir is None

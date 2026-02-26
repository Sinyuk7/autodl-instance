"""
集成测试专用 Fixtures

提供预配置的 AppContext，用于测试完整的 Pipeline 执行流程。
"""
import pytest
from pathlib import Path
from typing import Generator

from src.core.interface import AppContext
from src.core.artifacts import Artifacts
from src.main import load_manifests
from tests.mocks import MockRunner, MockStateManager


@pytest.fixture
def integration_project_root() -> Path:
    """返回真实项目根目录（用于加载 manifest.yaml）"""
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def integration_base_dir(tmp_path: Path) -> Path:
    """
    使用 pytest tmp_path 作为 base_dir
    
    创建必要的子目录结构，模拟 AutoDL 环境。
    """
    base = tmp_path / "autodl-tmp"
    base.mkdir(parents=True, exist_ok=True)
    
    # 创建 autodl-instance 目录（模拟项目部署位置）
    instance_dir = base / "autodl-instance"
    instance_dir.mkdir(parents=True, exist_ok=True)
    
    return base


@pytest.fixture
def integration_runner() -> MockRunner:
    """
    集成测试用的 MockRunner
    
    预设一些常见命令的返回值，确保插件逻辑能正常执行。
    """
    runner = MockRunner()
    
    # 预设常见命令的成功返回
    from src.core.ports import CommandResult
    
    # uv 相关
    runner.stub_results["uv --version"] = CommandResult(
        returncode=0, stdout="uv 0.1.0", stderr="", command="uv --version"
    )
    
    # git 相关
    runner.stub_results["git config"] = CommandResult(
        returncode=0, stdout="", stderr="", command="git config"
    )
    
    # comfy 相关
    runner.stub_results["comfy --version"] = CommandResult(
        returncode=0, stdout="comfy 1.0.0", stderr="", command="comfy --version"
    )
    
    return runner


@pytest.fixture
def integration_state() -> MockStateManager:
    """集成测试用的 MockStateManager（初始为空）"""
    return MockStateManager()


@pytest.fixture
def integration_context(
    integration_runner: MockRunner,
    integration_state: MockStateManager,
    integration_project_root: Path,
    integration_base_dir: Path,
) -> AppContext:
    """
    集成测试用的完整 AppContext
    
    - 使用真实的 project_root（加载真实 manifest.yaml）
    - 使用 tmp_path 作为 base_dir（隔离文件系统）
    - 使用 MockRunner（不执行真实命令）
    - 使用 MockStateManager（内存状态）
    """
    return AppContext(
        project_root=integration_project_root,
        base_dir=integration_base_dir,
        cmd=integration_runner,
        state=integration_state,
        artifacts=Artifacts(),
        debug=True,
        addon_manifests=load_manifests(integration_project_root),
    )


@pytest.fixture
def context_with_home(
    integration_context: AppContext,
    tmp_path: Path,
    monkeypatch,
) -> AppContext:
    """
    预设 HOME 目录的 context
    
    某些插件（如 SystemAddon）需要访问 ~/.local/bin 等路径，
    使用此 fixture 可避免污染真实 HOME 目录。
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    
    # 创建 .bashrc
    (fake_home / ".bashrc").touch()
    
    # 创建 .local/bin 目录（模拟 uv 已安装）
    uv_bin_dir = fake_home / ".local" / "bin"
    uv_bin_dir.mkdir(parents=True, exist_ok=True)
    (uv_bin_dir / "uv").touch()
    
    # Mock Path.home()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    
    return integration_context

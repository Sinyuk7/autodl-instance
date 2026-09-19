"""
Pytest 共享 Fixtures

提供可复用的测试上下文、mock 服务和临时文件系统。
"""
import pytest
from pathlib import Path

from src.core.interface import AppContext
from src.core.artifacts import Artifacts
from tests.mocks import MockRunner, MockStateManager


@pytest.fixture
def mock_runner() -> MockRunner:
    """新建一个干净的 MockRunner"""
    return MockRunner()


@pytest.fixture
def mock_state() -> MockStateManager:
    """新建一个干净的 MockStateManager"""
    return MockStateManager()


@pytest.fixture
def project_root() -> Path:
    """返回项目根目录"""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def tmp_base_dir(tmp_path: Path) -> Path:
    """使用 pytest tmp_path 作为 base_dir"""
    base = tmp_path / "autodl-tmp"
    base.mkdir(parents=True, exist_ok=True)
    return base


@pytest.fixture
def tmp_comfy_dir(tmp_path: Path) -> Path:
    """使用 pytest tmp_path 作为 comfy_dir"""
    comfy = tmp_path / "ComfyUI"
    comfy.mkdir(parents=True, exist_ok=True)
    return comfy


@pytest.fixture
def app_context(
    mock_runner: MockRunner,
    mock_state: MockStateManager,
    project_root: Path,
    tmp_base_dir: Path,
    tmp_comfy_dir: Path,
) -> AppContext:
    """
    构建一个完整的测试用 AppContext
    
    - 使用 MockRunner 替代 SubprocessRunner
    - 使用 MockStateManager 替代 FileStateManager
    - 使用 pytest tmp_path 作为 base_dir（避免污染真实文件系统）
    """
    return AppContext(
        project_root=project_root,
        base_dir=tmp_base_dir,
        comfy_dir=tmp_comfy_dir,
        cmd=mock_runner,
        state=mock_state,
        artifacts=Artifacts(),
        debug=True,
        python_env_dir=tmp_comfy_dir.parent / "venv",
        addon_manifests=__import__("src.main", fromlist=["load_manifests"]).load_manifests(project_root),
    )


@pytest.fixture
def context_with_comfy(app_context: AppContext, tmp_base_dir: Path) -> AppContext:
    """
    预设了 ComfyAddon 产出的上下文
    
    用于测试依赖 comfy_dir 的下游插件（workspace, models）
    """
    comfy_dir = tmp_base_dir / "ComfyUI"
    comfy_dir.mkdir(parents=True, exist_ok=True)
    (comfy_dir / "user").mkdir(parents=True, exist_ok=True)
    (comfy_dir / "models").mkdir(parents=True, exist_ok=True)
    
    app_context.artifacts.comfy_dir = comfy_dir
    app_context.artifacts.user_dir = comfy_dir / "user"
    
    return app_context

@pytest.fixture(autouse=True)
def isolate_process_state(monkeypatch, tmp_path):
    import os
    from unittest.mock import patch
    with patch.dict(os.environ, dict(os.environ), clear=True):
        for key in list(os.environ):
            if key.startswith("AUTODL_") or key in ("COMFYUI_MODELS_DIR", "CONDA_PREFIX", "VIRTUAL_ENV"):
                os.environ.pop(key, None)
        from src.core.runtime import DEFAULT_SECRETS_FILE
        from src.lib.utils import load_yaml
        with patch("src.core.runtime.load_local_secrets", side_effect=lambda path=DEFAULT_SECRETS_FILE: {} if path == DEFAULT_SECRETS_FILE else load_yaml(path)):
            yield


@pytest.fixture(autouse=True)
def fake_venv_for_addon_tests(request, tmp_path):
    if "app_context" in request.fixturenames:
        ctx = request.getfixturevalue("app_context")
        ctx.python_env_dir.mkdir(parents=True, exist_ok=True)
        (ctx.python_env_dir / "pyvenv.cfg").write_text("include-system-site-packages = false")

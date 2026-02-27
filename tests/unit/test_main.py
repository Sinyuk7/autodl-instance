"""
main.py 单元测试（精简版）

测试覆盖:
- load_manifests(): manifest.yaml 加载逻辑
- create_context(): 应用上下文创建
- main(): CLI 入口
"""
import pytest
from pathlib import Path
from unittest.mock import patch

from src.main import load_manifests, create_context, main, BASE_DIR
from src.core.interface import AppContext
from src.core.adapters import SubprocessRunner


class TestLoadManifests:
    """load_manifests() 测试"""

    @pytest.fixture
    def real_project_root(self) -> Path:
        """返回真实项目根目录"""
        return Path(__file__).resolve().parent.parent.parent

    def test_loads_manifests_correctly(self, real_project_root: Path):
        """应正确加载 addon 和 lib 的 manifest.yaml"""
        manifests = load_manifests(real_project_root)
        
        # 验证加载了 addon manifests
        assert "torch_engine" in manifests
        assert "system" in manifests
        # 验证加载了 lib manifests
        assert "download" in manifests
        # key 不应包含路径分隔符
        for key in manifests.keys():
            assert "/" not in key and "\\" not in key

    def test_missing_directory_returns_empty(self, tmp_path: Path):
        """目录不存在时返回空字典"""
        manifests = load_manifests(tmp_path / "non_existent")
        assert manifests == {}

    def test_empty_manifest_returns_empty_dict(self, tmp_path: Path):
        """空 YAML 文件返回空字典"""
        addons_dir = tmp_path / "src" / "addons" / "test_addon"
        addons_dir.mkdir(parents=True)
        (addons_dir / "manifest.yaml").write_text("")
        
        manifests = load_manifests(tmp_path)
        assert manifests.get("test_addon") == {}

    def test_skips_invalid_entries(self, tmp_path: Path):
        """应跳过非目录和无 manifest 的目录"""
        addons_dir = tmp_path / "src" / "addons"
        addons_dir.mkdir(parents=True)
        
        # 非目录文件
        (addons_dir / "some_file.txt").write_text("not a directory")
        # 无 manifest 的目录
        (addons_dir / "no_manifest").mkdir()
        # 有效目录
        valid_dir = addons_dir / "valid_addon"
        valid_dir.mkdir()
        (valid_dir / "manifest.yaml").write_text("key: value")
        
        manifests = load_manifests(tmp_path)
        assert "valid_addon" in manifests
        assert "some_file.txt" not in manifests
        assert "no_manifest" not in manifests


class TestCreateContext:
    """create_context() 测试"""

    @pytest.fixture
    def mock_file_state_manager(self):
        """Mock FileStateManager 避免文件系统操作"""
        with patch("src.main.FileStateManager") as mock_cls:
            mock_cls.return_value._base_dir = BASE_DIR
            yield mock_cls

    def test_returns_valid_app_context(self, mock_file_state_manager):
        """应返回正确配置的 AppContext"""
        with patch("src.main.load_manifests", return_value={"test": {}}):
            ctx = create_context()
        
        assert isinstance(ctx, AppContext)
        assert ctx.base_dir == BASE_DIR
        assert isinstance(ctx.cmd, SubprocessRunner)
        assert ctx.addon_manifests == {"test": {}}

    @pytest.mark.parametrize("debug", [False, True])
    def test_debug_flag_propagates(self, mock_file_state_manager, debug):
        """debug 参数正确传递"""
        with patch("src.main.load_manifests", return_value={}):
            ctx = create_context(debug=debug)
        assert ctx.debug == debug

    def test_manifests_are_loaded(self, mock_file_state_manager):
        """addon_manifests 应已预加载"""
        fake_manifests = {"torch_engine": {"key": "value"}}
        with patch("src.main.load_manifests", return_value=fake_manifests):
            ctx = create_context()
        assert ctx.addon_manifests == fake_manifests


class TestMain:
    """main() CLI 入口测试"""

    @pytest.fixture
    def mock_dependencies(self):
        """Mock 所有外部依赖"""
        with patch("src.main.setup_logger"), \
             patch("src.main.kill_process_by_name"), \
             patch("src.main.setup_network"), \
             patch("src.main.create_context") as mock_ctx, \
             patch("src.main.execute") as mock_exec:
            yield {"create_context": mock_ctx, "execute": mock_exec}

    @pytest.mark.parametrize("action", ["setup", "start", "sync"])
    def test_valid_actions(self, mock_dependencies, monkeypatch, action):
        """有效 action 正确传递给 execute"""
        monkeypatch.setattr("sys.argv", ["main.py", action])
        main()
        assert mock_dependencies["execute"].call_args[0][0] == action

    def test_invalid_action_rejected(self, mock_dependencies, monkeypatch):
        """无效 action 被 argparse 拒绝"""
        monkeypatch.setattr("sys.argv", ["main.py", "invalid"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    @pytest.mark.parametrize("args,expected", [
        (["main.py", "setup"], False),
        (["main.py", "setup", "--debug"], True),
    ])
    def test_debug_flag(self, mock_dependencies, monkeypatch, args, expected):
        """--debug 参数正确传递"""
        monkeypatch.setattr("sys.argv", args)
        main()
        assert mock_dependencies["create_context"].call_args[1]["debug"] == expected

    def test_until_parameter(self, mock_dependencies, monkeypatch):
        """--until 参数正确传递"""
        monkeypatch.setattr("sys.argv", ["main.py", "setup", "--until", "comfy_core"])
        main()
        assert mock_dependencies["execute"].call_args[1]["until"] == "comfy_core"

    def test_only_parameter(self, mock_dependencies, monkeypatch):
        """--only 参数正确传递"""
        monkeypatch.setattr("sys.argv", ["main.py", "setup", "--only", "system"])
        main()
        assert mock_dependencies["execute"].call_args[1]["only"] == "system"

    def test_execution_order(self, monkeypatch):
        """初始化顺序: logger → kill → network → context → execute"""
        call_order = []
        
        with patch("src.main.setup_logger", side_effect=lambda *a, **kw: call_order.append("logger")), \
             patch("src.main.kill_process_by_name", side_effect=lambda *a, **kw: call_order.append("kill")), \
             patch("src.main.setup_network", side_effect=lambda: call_order.append("network")), \
             patch("src.main.create_context", side_effect=lambda **kw: call_order.append("context")), \
             patch("src.main.execute", side_effect=lambda *a, **kw: call_order.append("execute")):
            
            monkeypatch.setattr("sys.argv", ["main.py", "setup"])
            main()
        
        assert call_order == ["logger", "kill", "network", "context", "execute"]
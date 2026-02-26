"""
SystemAddon 单元测试
"""
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from src.addons.system.plugin import SystemAddon
from src.core.interface import AppContext


class TestInstallUv:
    """_install_uv 方法测试"""

    def test_install_uv_when_not_exists(
        self, app_context: AppContext, mock_runner, tmp_path: Path, monkeypatch
    ):
        """uv 不存在时应执行安装脚本"""
        # 设置 home 目录为临时目录
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        addon = SystemAddon()
        addon._install_uv(app_context)
        
        # 验证调用了 curl 安装脚本
        assert mock_runner.was_called_with_pattern("curl.*uv/install.sh")

    def test_install_uv_skip_when_exists(
        self, app_context: AppContext, mock_runner, tmp_path: Path, monkeypatch
    ):
        """uv 已存在时应跳过安装"""
        # 设置 home 目录并创建 uv
        fake_home = tmp_path / "home"
        uv_path = fake_home / ".local" / "bin"
        uv_path.mkdir(parents=True)
        (uv_path / "uv").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        addon = SystemAddon()
        addon._install_uv(app_context)
        
        # 验证未调用安装命令
        assert not mock_runner.was_called_with_pattern("curl")

    def test_install_uv_updates_path_env(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """应将 uv 路径添加到 PATH 环境变量"""
        fake_home = tmp_path / "home"
        uv_path = fake_home / ".local" / "bin"
        uv_path.mkdir(parents=True)
        (uv_path / "uv").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        # 清空 PATH 中可能存在的 uv 路径
        original_path = os.environ.get("PATH", "")
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        
        addon = SystemAddon()
        addon._install_uv(app_context)
        
        # 验证 PATH 被更新
        assert str(uv_path) in os.environ["PATH"]

    def test_install_uv_sets_uv_bin_artifact(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """应正确设置 ctx.artifacts.uv_bin"""
        fake_home = tmp_path / "home"
        uv_path = fake_home / ".local" / "bin"
        uv_path.mkdir(parents=True)
        (uv_path / "uv").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        addon = SystemAddon()
        addon._install_uv(app_context)
        
        assert app_context.artifacts.uv_bin == uv_path / "uv"


class TestGenerateBinScripts:
    """_generate_bin_scripts 方法测试"""

    def test_creates_bin_directory(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """应创建 bin 目录"""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".bashrc").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        addon = SystemAddon()
        addon._generate_bin_scripts(app_context)
        
        bin_dir = app_context.base_dir / "autodl-instance" / "bin"
        assert bin_dir.exists()
        assert bin_dir.is_dir()

    def test_creates_all_scripts(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """应生成 turbo, bye, model, start 四个脚本"""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".bashrc").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        addon = SystemAddon()
        addon._generate_bin_scripts(app_context)
        
        bin_dir = app_context.base_dir / "autodl-instance" / "bin"
        expected_scripts = ["turbo", "bye", "model", "start"]
        
        for script_name in expected_scripts:
            assert (bin_dir / script_name).exists(), f"脚本 {script_name} 未生成"

    def test_correct_permissions(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """脚本应具有可执行权限 (0o755)"""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".bashrc").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        addon = SystemAddon()
        addon._generate_bin_scripts(app_context)
        
        bin_dir = app_context.base_dir / "autodl-instance" / "bin"
        
        for script_name in ["turbo", "bye", "model", "start"]:
            script_path = bin_dir / script_name
            mode = script_path.stat().st_mode
            # 检查可执行权限
            assert mode & stat.S_IXUSR, f"{script_name} 缺少用户可执行权限"
            assert mode & stat.S_IXGRP, f"{script_name} 缺少组可执行权限"
            assert mode & stat.S_IXOTH, f"{script_name} 缺少其他用户可执行权限"

    def test_correct_content(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """脚本内容应包含正确的路径"""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".bashrc").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        addon = SystemAddon()
        addon._generate_bin_scripts(app_context)
        
        bin_dir = app_context.base_dir / "autodl-instance" / "bin"
        project_dir = app_context.base_dir / "autodl-instance"
        
        # 验证 turbo 脚本内容
        turbo_content = (bin_dir / "turbo").read_text()
        assert "#!/bin/bash" in turbo_content
        assert str(project_dir) in turbo_content
        assert "python -m src.lib.network" in turbo_content
        
        # 验证 start 脚本内容
        start_content = (bin_dir / "start").read_text()
        assert "python -m src.main start" in start_content

    def test_updates_bashrc_when_not_configured(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """bin 目录不在 .bashrc 中时应添加"""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        bashrc = fake_home / ".bashrc"
        bashrc.write_text("# 原有内容\n")
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        addon = SystemAddon()
        addon._generate_bin_scripts(app_context)
        
        bashrc_content = bashrc.read_text()
        bin_dir = app_context.base_dir / "autodl-instance" / "bin"
        
        assert str(bin_dir) in bashrc_content
        assert "export PATH=" in bashrc_content

    def test_skip_bashrc_when_already_configured(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """bin 目录已在 .bashrc 中时应跳过"""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        bin_dir = app_context.base_dir / "autodl-instance" / "bin"
        bashrc = fake_home / ".bashrc"
        bashrc.write_text(f"# 原有内容\nexport PATH=\"{bin_dir}:$PATH\"\n")
        original_content = bashrc.read_text()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        addon = SystemAddon()
        addon._generate_bin_scripts(app_context)
        
        # 内容应该没有重复添加
        bashrc_content = bashrc.read_text()
        assert bashrc_content.count(str(bin_dir)) == 1

    def test_sets_bin_dir_artifact(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """应正确设置 ctx.artifacts.bin_dir"""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".bashrc").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        addon = SystemAddon()
        addon._generate_bin_scripts(app_context)
        
        expected_bin_dir = app_context.base_dir / "autodl-instance" / "bin"
        assert app_context.artifacts.bin_dir == expected_bin_dir


class TestHooks:
    """钩子方法测试"""

    def test_start_does_nothing(self, app_context: AppContext):
        """start 方法应为空实现"""
        addon = SystemAddon()
        # 不应抛出异常
        addon.start(app_context)

    def test_sync_does_nothing(self, app_context: AppContext):
        """sync 方法应为空实现"""
        addon = SystemAddon()
        # 不应抛出异常
        addon.sync(app_context)


class TestPipelineIntegration:
    """Pipeline 集成测试 - 通过 main.execute() 执行 SystemAddon"""

    def test_until_system_only_runs_system(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """--until system 应只执行 SystemAddon"""
        from unittest.mock import patch
        from src.main import create_pipeline, execute
        
        # Mock home 目录
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".bashrc").touch()
        uv_path = fake_home / ".local" / "bin"
        uv_path.mkdir(parents=True)
        (uv_path / "uv").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        called_addons = []
        
        # 追踪哪些插件被执行
        original_pipeline = create_pipeline()
        for addon in original_pipeline:
            original_setup = addon.setup
            def make_tracker(name, orig):
                def tracked_setup(context):
                    called_addons.append(name)
                    return orig(context)
                return tracked_setup
            addon.setup = make_tracker(addon.name, original_setup)
        
        with patch("src.main.create_pipeline", return_value=original_pipeline):
            execute("setup", app_context, until="system")
        
        assert called_addons == ["system"]
        # 验证 SystemAddon 产出
        assert app_context.artifacts.uv_bin is not None
        assert app_context.artifacts.bin_dir is not None

    def test_only_system_runs_system_setup(
        self, app_context: AppContext, tmp_path: Path, monkeypatch
    ):
        """--only system 应只执行 SystemAddon.setup()"""
        from src.main import execute
        
        # Mock home 目录
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".bashrc").touch()
        uv_path = fake_home / ".local" / "bin"
        uv_path.mkdir(parents=True)
        (uv_path / "uv").touch()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        
        execute("setup", app_context, only="system")
        
        # 验证 SystemAddon 产出
        assert app_context.artifacts.uv_bin == uv_path / "uv"
        expected_bin_dir = app_context.base_dir / "autodl-instance" / "bin"
        assert app_context.artifacts.bin_dir == expected_bin_dir
        assert expected_bin_dir.exists()
        
        # 验证其他插件产出未设置
        assert app_context.artifacts.comfy_dir is None

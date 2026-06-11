"""GitAddon 单元测试"""
import base64
from pathlib import Path
from unittest.mock import patch

import pytest

from src.addons.git_config.plugin import GitAddon
from src.core.interface import AppContext
from src.core.ports import CommandResult


class TestSetup:
    """setup 钩子测试"""

    def test_fresh_install_success(
        self, app_context: AppContext, mock_runner, tmp_path: Path, monkeypatch
    ):
        """全新安装：应配置 Git 身份、生成 SSH 密钥，设置 artifacts"""
        app_context.addon_manifests["git_config"] = {
            "user_name": "Test User",
            "user_email": "test@example.com",
        }

        # Mock SSH 系统目录
        fake_system_ssh = tmp_path / "system_ssh"
        addon = GitAddon()
        monkeypatch.setattr(addon, "SSH_SYSTEM_DIR", fake_system_ssh)

        # Mock GitHub 连接测试成功
        mock_runner.stub_results["ssh -T"] = CommandResult(
            returncode=1, stdout="", stderr="Hi user! You've successfully authenticated",
            command="ssh -T",
        )

        with patch.object(addon, "_generate_ssh_key"):
            addon.setup(app_context)

        # 验证 artifacts
        assert app_context.artifacts.ssh_dir == app_context.base_dir / ".ssh"

    def test_skip_when_no_identity_configured(
        self, app_context: AppContext, mock_runner
    ):
        """未配置 Git 身份时应跳过整个流程"""
        addon = GitAddon()
        addon.setup(app_context)

        # 不应执行 Git 配置
        mock_runner.assert_not_called_with("git config")
        # artifacts 不应设置
        assert app_context.artifacts.ssh_dir is None

    def test_skip_when_only_name_configured(
        self, app_context: AppContext, mock_runner
    ):
        """只配置用户名时应跳过"""
        app_context.addon_manifests["git_config"] = {
            "user_name": "Test User",
        }

        addon = GitAddon()
        addon.setup(app_context)

        assert app_context.artifacts.ssh_dir is None

    def test_reuses_existing_ssh_key(
        self, app_context: AppContext, mock_runner, tmp_path: Path, monkeypatch
    ):
        """已有 SSH 密钥时应复用"""
        app_context.addon_manifests["git_config"] = {
            "user_name": "Test User",
            "user_email": "test@example.com",
        }

        # 创建已有密钥
        ssh_dir = app_context.base_dir / ".ssh"
        ssh_dir.mkdir(parents=True)
        (ssh_dir / "id_ed25519").write_text("existing_key")
        (ssh_dir / "id_ed25519.pub").write_text("existing_pub_key")

        fake_system_ssh = tmp_path / "system_ssh"
        addon = GitAddon()
        monkeypatch.setattr(addon, "SSH_SYSTEM_DIR", fake_system_ssh)

        mock_runner.stub_results["ssh -T"] = CommandResult(
            returncode=1, stdout="", stderr="Hi user!", command="ssh -T",
        )

        addon.setup(app_context)

        # 验证未生成新密钥
        mock_runner.assert_not_called_with("ssh-keygen -t ed25519")
        # 密钥未被修改
        assert (ssh_dir / "id_ed25519").read_text() == "existing_key"

    def test_injects_key_from_manifest(
        self, app_context: AppContext, mock_runner, tmp_path: Path, monkeypatch
    ):
        """应从 manifest 注入 SSH 密钥"""
        private_key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----"
        private_key_b64 = base64.b64encode(private_key_content.encode()).decode()

        app_context.addon_manifests["git_config"] = {
            "user_name": "Test User",
            "user_email": "test@example.com",
            "ssh_private_key": private_key_b64,
            "ssh_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample",
        }

        fake_system_ssh = tmp_path / "system_ssh"
        addon = GitAddon()
        monkeypatch.setattr(addon, "SSH_SYSTEM_DIR", fake_system_ssh)

        mock_runner.stub_results["ssh -T"] = CommandResult(
            returncode=1, stdout="", stderr="Hi user!", command="ssh -T",
        )

        addon.setup(app_context)

        # 验证密钥已注入
        ssh_dir = app_context.base_dir / ".ssh"
        assert (ssh_dir / "id_ed25519").read_text() == private_key_content

    def test_identity_priority_env_then_local_config_then_manifest(
        self, app_context: AppContext, mock_runner, monkeypatch
    ):
        app_context.addon_manifests["git_config"] = {
            "user_name": "Manifest User",
            "user_email": "manifest@example.com",
        }
        app_context.local_config["git_user_name"] = "Config User"
        app_context.local_config["git_user_email"] = "config@example.com"
        monkeypatch.setenv("GIT_USER_NAME", "Env User")
        monkeypatch.setenv("GIT_USER_EMAIL", "env@example.com")

        addon = GitAddon()
        with patch.object(addon, "_ensure_ssh_key"), patch.object(addon, "_test_github_connection"):
            addon.setup(app_context)

        assert any("git config --global user.name Env User" == cmd for cmd in mock_runner.all_commands)
        assert any("git config --global user.email env@example.com" == cmd for cmd in mock_runner.all_commands)

    def test_identity_uses_local_config_before_manifest(
        self, app_context: AppContext, mock_runner, monkeypatch
    ):
        monkeypatch.delenv("GIT_USER_NAME", raising=False)
        monkeypatch.delenv("GIT_USER_EMAIL", raising=False)
        app_context.addon_manifests["git_config"] = {
            "user_name": "Manifest User",
            "user_email": "manifest@example.com",
        }
        app_context.local_config["git_user_name"] = "Config User"
        app_context.local_config["git_user_email"] = "config@example.com"

        addon = GitAddon()
        with patch.object(addon, "_ensure_ssh_key"), patch.object(addon, "_test_github_connection"):
            addon.setup(app_context)

        assert any("git config --global user.name Config User" == cmd for cmd in mock_runner.all_commands)
        assert any("git config --global user.email config@example.com" == cmd for cmd in mock_runner.all_commands)


class TestStart:
    """start 钩子测试"""

    def test_start_does_nothing(self, app_context: AppContext):
        """start 为空实现"""
        addon = GitAddon()
        addon.start(app_context)  # 不应抛出异常


class TestSync:
    """sync 钩子测试"""

    def test_sync_does_nothing(self, app_context: AppContext):
        """sync 为空实现"""
        addon = GitAddon()
        addon.sync(app_context)  # 不应抛出异常

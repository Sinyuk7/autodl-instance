"""
Mock 实现的自测

验证 MockRunner 和 MockStateManager 行为正确。
"""
import pytest
from pathlib import Path

from src.core.ports import CommandResult
from tests.mocks import MockRunner, MockStateManager


class TestMockRunner:
    """MockRunner 测试"""

    def test_default_success(self):
        runner = MockRunner()
        result = runner.run(["echo", "hello"])
        assert result.returncode == 0
        assert result.command == "echo hello"

    def test_records_calls(self):
        runner = MockRunner()
        runner.run(["git", "status"])
        runner.run(["pip", "install", "torch"])
        assert len(runner.calls) == 2
        assert runner.calls[0].cmd == "git status"
        assert runner.calls[1].cmd == "pip install torch"

    def test_stub_results(self):
        runner = MockRunner()
        runner.stub_results["nvidia-smi"] = CommandResult(
            returncode=0,
            stdout="CUDA 12.1",
            stderr="",
            command="nvidia-smi",
        )

        result = runner.run(["nvidia-smi"])
        assert result.stdout == "CUDA 12.1"

    def test_prefix_matching(self):
        runner = MockRunner()
        runner.stub_results["git clone"] = CommandResult(
            returncode=0, stdout="ok", stderr="", command="git clone"
        )

        result = runner.run(["git", "clone", "--depth", "1", "https://example.com"])
        assert result.stdout == "ok"

    def test_realtime_records(self):
        runner = MockRunner()
        rc = runner.run_realtime(["pip", "install", "torch"])
        assert rc == 0
        assert len(runner.realtime_calls) == 1

    def test_assert_called_with(self):
        runner = MockRunner()
        runner.run(["git", "clone", "https://example.com"])
        call = runner.assert_called_with("git clone")
        assert call.cmd == "git clone https://example.com"

    def test_assert_called_with_fails(self):
        runner = MockRunner()
        runner.run(["git", "status"])
        with pytest.raises(AssertionError, match="没有找到"):
            runner.assert_called_with("pip install")

    def test_assert_not_called_with(self):
        runner = MockRunner()
        runner.run(["git", "status"])
        runner.assert_not_called_with("pip")

    def test_assert_not_called_with_fails(self):
        runner = MockRunner()
        runner.run(["pip", "install", "torch"])
        with pytest.raises(AssertionError, match="意外发现"):
            runner.assert_not_called_with("pip")

    def test_all_commands(self):
        runner = MockRunner()
        runner.run(["cmd1"])
        runner.run_realtime(["cmd2"])
        assert runner.all_commands == ["cmd1", "cmd2"]

    def test_cwd_recorded(self):
        runner = MockRunner()
        runner.run(["ls"], cwd=Path("/tmp"))
        assert runner.calls[0].cwd == Path("/tmp")


class TestMockStateManager:
    """MockStateManager 测试"""

    def test_initially_empty(self):
        state = MockStateManager()
        assert not state.is_completed("foo")

    def test_mark_and_check(self):
        state = MockStateManager()
        state.mark_completed("foo")
        assert state.is_completed("foo")
        assert not state.is_completed("bar")

    def test_clear(self):
        state = MockStateManager()
        state.mark_completed("foo")
        state.clear("foo")
        assert not state.is_completed("foo")

    def test_pre_completed(self):
        state = MockStateManager(pre_completed={"foo", "bar"})
        assert state.is_completed("foo")
        assert state.is_completed("bar")
        assert not state.is_completed("baz")

    def test_enum_support(self):
        """支持 Enum value"""
        from src.core.schema import StateKey
        state = MockStateManager()
        state.mark_completed(StateKey.COMFY_INSTALLED)
        assert state.is_completed(StateKey.COMFY_INSTALLED)

    def test_completed_keys(self):
        state = MockStateManager()
        state.mark_completed("a")
        state.mark_completed("b")
        assert state.completed_keys == {"a", "b"}

from pathlib import Path

from src.addons.userdata.strategy import GitRepoStrategy, LocalStrategy
from src.core.ports import CommandResult


def test_local_strategy_push_returns_warning(app_context, tmp_path: Path):
    data_dir = tmp_path / "my-comfyui-backup"
    data_dir.mkdir()
    strategy = LocalStrategy(tmp_path / "example")

    result = strategy.push(data_dir, app_context)

    assert result.status == "warning"
    assert "本地" in result.message


def test_git_strategy_push_success(app_context, mock_runner, tmp_path: Path):
    data_dir = tmp_path / "repo"
    (data_dir / ".git").mkdir(parents=True)
    strategy = GitRepoStrategy("git@example.com:repo.git", "repo", mock_runner)
    mock_runner.stub_results["git status --porcelain"] = CommandResult(
        0, " M user/settings.json\n", "", "git status --porcelain"
    )
    mock_runner.stub_results["git add ."] = CommandResult(0, "", "", "git add .")
    mock_runner.stub_results["git commit"] = CommandResult(0, "ok", "", "git commit")
    mock_runner.stub_results["git push"] = CommandResult(0, "pushed", "", "git push")

    result = strategy.push(data_dir, app_context)

    assert result.status == "success"
    assert mock_runner.was_called_with_pattern("git push")


def test_git_strategy_push_failure_is_critical(app_context, mock_runner, tmp_path: Path):
    data_dir = tmp_path / "repo"
    (data_dir / ".git").mkdir(parents=True)
    strategy = GitRepoStrategy("git@example.com:repo.git", "repo", mock_runner)
    mock_runner.stub_results["git status --porcelain"] = CommandResult(
        0, " M user/settings.json\n", "", "git status --porcelain"
    )
    mock_runner.stub_results["git add ."] = CommandResult(0, "", "", "git add .")
    mock_runner.stub_results["git commit"] = CommandResult(0, "ok", "", "git commit")
    mock_runner.stub_results["git push"] = CommandResult(1, "", "permission denied", "git push")

    result = strategy.push(data_dir, app_context)

    assert result.status == "failure"
    assert "Git push 失败" in result.message
    assert "git status && git push" in result.next_step

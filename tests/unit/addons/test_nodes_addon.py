from unittest.mock import patch

from src.addons.nodes.plugin import NodesAddon


def test_node_dependencies_use_comfyui_python(context_with_comfy, mock_runner, tmp_path):
    node = context_with_comfy.artifacts.custom_nodes_dir / "example"
    node.mkdir()
    requirements = node / "requirements.txt"
    requirements.write_text("example-package==1.0\n", encoding="utf-8")
    target_python = str(tmp_path / "miniconda3" / "bin" / "python3")

    with patch("src.addons.nodes.plugin.resolve_target_python", return_value=target_python):
        NodesAddon()._install_node_dependencies(context_with_comfy)

    call = mock_runner.assert_called_with(target_python)
    assert f"-m pip install -r {requirements}" in call.cmd

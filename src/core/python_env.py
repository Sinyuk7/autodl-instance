"""Resolve the Python environment shared by ComfyUI and its addons."""
import sys
import shutil
from pathlib import Path


def resolve_target_python(env_dir: Path = Path('/root/.venvs/comfyui')) -> str:
    """Never fall back to the platform Conda environment."""
    return str(env_dir / 'bin/python')


def ensure_python_env(ctx) -> None:
    env_dir = ctx.python_env_dir
    validate_env_path(env_dir)
    if env_dir.is_symlink():
        raise ValueError("Python environment directory cannot be a symlink")
    if env_dir.exists() and not (env_dir / 'pyvenv.cfg').is_file():
        raise RuntimeError(f'Refusing to overwrite non-venv directory: {env_dir}')
    if not (env_dir / 'pyvenv.cfg').exists():
        parent = env_dir.parent
        while not parent.exists():
            parent = parent.parent
        if shutil.disk_usage(parent).free < 5 * 1024**3:
            raise RuntimeError("Less than 5 GiB free on Python environment disk")
        ctx.cmd.run([str(ctx.artifacts.uv_bin), 'venv', '--python', sys.executable,
                     '--seed', str(env_dir)], check=True)
    ctx.cmd.run([resolve_target_python(env_dir), '-c',
                 'import sys; from pathlib import Path; '
                 'assert sys.prefix != sys.base_prefix; '
                 'assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve()', str(env_dir)], check=True)

def validate_env_path(env_dir: Path) -> None:
    from src.core.runtime import MANAGED_STORAGE_ROOTS
    resolved = env_dir.resolve()
    if resolved in (Path("/"), Path.home(), Path(sys.base_prefix).resolve()):
        raise ValueError(f"Unsafe Python environment path: {env_dir}")
    for root in MANAGED_STORAGE_ROOTS:
        if resolved == root.resolve() or root.resolve() in resolved.parents:
            raise ValueError("ComfyUI Python environment must stay on the system disk")

"""Torch engine addon for preparing a CUDA-capable PyTorch environment."""

from src.addons.torch_engine.tasks import FixCudaDependencyChainTask
from src.core.interface import AppContext, BaseAddon, hookimpl
from src.core.python_env import resolve_target_python
from src.core.task import BaseTask, TaskRunner
from src.core.utils import logger


class TorchAddon(BaseAddon):
    module_dir = "torch_engine"

    def get_tasks(self, phase: str) -> list[BaseTask]:
        if phase == "setup":
            return [FixCudaDependencyChainTask()]
        return []

    def _get_torch_cuda_info(self, ctx: AppContext, python_executable: str) -> str:
        check_script = (
            "import sys\n"
            "try:\n"
            "    import torch\n"
            "    cuda_ver = torch.version.cuda\n"
            "    try:\n"
            "        cuda_float = float(cuda_ver) if cuda_ver else None\n"
            "    except:\n"
            '        cuda_float = "parse_error"\n'
            '    print(f"torch={torch.__version__}, "'
            'f"cuda_raw={repr(cuda_ver)}, cuda_float={cuda_float}", end="")\n'
            "except Exception as e:\n"
            '    print(f"error={e}", end="")\n'
        )
        result = ctx.cmd.run(
            [python_executable, "-c", check_script],
            check=False,
        )
        return result.stdout.strip() or result.stderr.strip()

    def _is_torch_cuda_ready(
        self,
        ctx: AppContext,
        min_cuda_version: float,
        python_executable: str,
    ) -> bool:
        check_script = (
            "import sys\n"
            "try:\n"
            "    import torch\n"
            "    cuda_ver = torch.version.cuda\n"
            f"    if cuda_ver and float(cuda_ver) >= {min_cuda_version}:\n"
            "        sys.exit(0)\n"
            "    sys.exit(1)\n"
            "except Exception as e:\n"
            '    print(f"EXCEPTION: {type(e).__name__}: {e}", file=sys.stderr)\n'
            "    sys.exit(1)\n"
        )
        result = ctx.cmd.run(
            [python_executable, "-c", check_script],
            check=False,
        )
        logger.debug(
            "  -> [DEBUG] _is_torch_cuda_ready: returncode=%s",
            result.returncode,
        )
        return result.returncode == 0

    @hookimpl
    def setup(self, context: AppContext) -> None:
        logger.info("\n>>> [Torch Engine] Starting torch runtime setup...")

        tasks = self.get_tasks("setup")
        if tasks and not TaskRunner.run_tasks(tasks, context, self.name):
            raise RuntimeError(f"[{self.name}] setup tasks failed")

        cfg = self.get_manifest(context)
        self.min_driver = cfg.get("min_driver_version", 580)
        self.min_cuda = cfg.get("min_cuda_version", 13.0)
        self.index_url = cfg.get(
            "index_url", "https://download.pytorch.org/whl/cu130"
        )
        self.packages = cfg.get("packages", ["torch", "torchvision", "torchaudio"])

        logger.info("  -> Driver >= %s, CUDA >= %s", self.min_driver, self.min_cuda)
        logger.info("  -> Using package index: %s", self.index_url)

        target_python = resolve_target_python()
        logger.info("  -> Target Python: %s", target_python)
        is_ready = self._is_torch_cuda_ready(context, self.min_cuda, target_python)
        cuda_info = self._get_torch_cuda_info(context, target_python)
        logger.debug(
            "  -> [DEBUG] Torch readiness: is_ready=%s, cuda_info=%s",
            is_ready,
            cuda_info,
        )

        if is_ready:
            logger.info(
                "  -> [SKIP] PyTorch (CUDA >= %s) is already ready.",
                self.min_cuda,
            )
            context.artifacts.torch_installed = True
            return

        self._check_driver_version(context)
        self._install_torch(context, target_python)
        context.artifacts.torch_installed = True

    def _check_driver_version(self, ctx: AppContext) -> None:
        try:
            result = ctx.cmd.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                check=True,
            )
            version_str = result.stdout.strip().split("\n")[0]
            major_version = int(version_str.split(".")[0])
            logger.info("  -> Host driver version: %s", version_str)
            if major_version < self.min_driver:
                raise RuntimeError(
                    f"NVIDIA driver {version_str} is below required {self.min_driver}"
                )
        except FileNotFoundError:
            logger.info("  -> [INFO] GPU not detected, skipping driver validation.")

    def _install_torch(self, ctx: AppContext, python_executable: str) -> None:
        logger.info("  -> Installing PyTorch with uv...")
        command = ["uv", "pip", "install", "--python", python_executable]
        command.extend(self.packages)
        command.extend(["--index-url", self.index_url])

        returncode = ctx.cmd.run_realtime(command)
        if returncode != 0:
            raise RuntimeError(
                f"Torch install failed, exit code: {returncode}, "
                f"command: {' '.join(command)}"
            )
        logger.info("  -> Torch runtime installation completed.")

    @hookimpl
    def start(self, context: AppContext) -> None:
        return None

    @hookimpl
    def stop(self, context: AppContext) -> None:
        return None

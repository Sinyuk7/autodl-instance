"""
Torch engine addon for preparing a CUDA-capable PyTorch environment.
"""
import sys
from typing import List

from src.addons.torch_engine.tasks import FixCudaDependencyChainTask
from src.core.interface import AppContext, BaseAddon, hookimpl
from src.core.task import BaseTask, TaskRunner
from src.core.utils import logger


class TorchAddon(BaseAddon):
    module_dir = "torch_engine"

    def get_tasks(self, phase: str) -> List[BaseTask]:
        """Return task hooks for the requested lifecycle phase."""
        if phase == "setup":
            return [
                FixCudaDependencyChainTask(),
            ]
        return []

    def _get_torch_cuda_info(self, ctx: AppContext) -> str:
        """Collect current torch/CUDA details for debug logging."""
        check_script = (
            "import sys\n"
            "try:\n"
            "    import torch\n"
            "    cuda_ver = torch.version.cuda\n"
            "    try:\n"
            "        cuda_float = float(cuda_ver) if cuda_ver else None\n"
            "    except:\n"
            '        cuda_float = "parse_error"\n'
            '    print(f"torch={torch.__version__}, cuda_raw={repr(cuda_ver)}, cuda_float={cuda_float}", end="")\n'
            "except Exception as e:\n"
            '    print(f"error={e}", end="")\n'
        )
        result = ctx.cmd.run(
            [sys.executable, "-c", check_script],
            check=False,
        )
        return result.stdout.strip() or result.stderr.strip()

    def _is_torch_cuda_ready(self, ctx: AppContext, min_cuda_version: float) -> bool:
        """Check whether torch is already installed with a sufficient CUDA runtime."""
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
            [sys.executable, "-c", check_script],
            check=False,
        )
        logger.debug(f"  -> [DEBUG] _is_torch_cuda_ready: returncode={result.returncode}")
        return result.returncode == 0

    @hookimpl
    def setup(self, context: AppContext) -> None:
        logger.info("\n>>> [Torch Engine] Starting torch runtime setup...")
        ctx = context

        tasks = self.get_tasks("setup")
        if tasks and not TaskRunner.run_tasks(tasks, ctx, self.name):
            raise RuntimeError(f"[{self.name}] setup tasks failed")

        cfg = self.get_manifest(ctx)
        self.min_driver = cfg.get("min_driver_version", 580)
        self.min_cuda = cfg.get("min_cuda_version", 13.0)
        self.index_url = cfg.get("index_url", "https://download.pytorch.org/whl/cu130")
        self.packages = cfg.get("packages", ["torch", "torchvision", "torchaudio"])

        logger.info(f"  -> Driver >= {self.min_driver}, CUDA >= {self.min_cuda}")
        logger.info(f"  -> Using package index: {self.index_url}")

        is_ready = self._is_torch_cuda_ready(ctx, self.min_cuda)
        cuda_info = self._get_torch_cuda_info(ctx)
        logger.debug(f"  -> [DEBUG] Torch readiness: is_ready={is_ready}, cuda_info={cuda_info}")

        if is_ready:
            logger.info(f"  -> [SKIP] PyTorch (CUDA >= {self.min_cuda}) is already ready.")
            ctx.artifacts.torch_installed = True
            return

        self._check_driver_version(ctx)
        self._install_torch(ctx)
        ctx.artifacts.torch_installed = True

    def _check_driver_version(self, ctx: AppContext) -> None:
        """Validate the NVIDIA driver major version when a GPU is present."""
        try:
            res = ctx.cmd.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                check=True,
            )
            version_str = res.stdout.strip().split("\n")[0]
            major_version = int(version_str.split(".")[0])

            logger.info(f"  -> Host driver version: {version_str}")
            if major_version < self.min_driver:
                logger.error(f"  -> [ERROR] CUDA driver must be >= {self.min_driver}")
                sys.exit(1)
        except FileNotFoundError:
            logger.info("  -> [INFO] GPU not detected, skipping driver validation.")
        except Exception as e:
            logger.warning(f"  -> [WARN] Driver validation failed, continuing: {e}")

    def _install_torch(self, ctx: AppContext) -> None:
        """Install PyTorch from the configured CUDA wheel index."""
        logger.info("  -> Installing PyTorch with uv...")

        cmd = ["uv", "pip", "install", "--system", "--upgrade"]
        cmd.extend(self.packages)
        cmd.extend(["--index-url", self.index_url])

        returncode = ctx.cmd.run_realtime(cmd)
        if returncode != 0:
            raise RuntimeError(f"Torch install failed, exit code: {returncode}, command: {' '.join(cmd)}")

        logger.info("  -> Torch runtime installation completed.")

    @hookimpl
    def start(self, context: AppContext) -> None:
        pass

    @hookimpl
    def stop(self, context: AppContext) -> None:
        pass

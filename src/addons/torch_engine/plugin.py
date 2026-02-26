"""
Torch Engine Addon - PyTorch CUDA 环境装配
"""
import sys

from src.core.interface import BaseAddon, AppContext, hookimpl
from src.core.schema import StateKey
from src.core.utils import logger


class TorchAddon(BaseAddon):
    module_dir = "torch_engine"

    def _get_torch_cuda_info(self, ctx: AppContext) -> str:
        """获取当前 Torch 的版本和 CUDA 信息用于调试"""
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
        """检查 PyTorch 是否已安装且 CUDA 版本满足要求"""
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
        logger.info("\n>>> [Torch Engine] 开始装配底层算力引擎...")
        ctx = context

        # 1. 提取配置 (从 manifest.yaml)
        cfg = self.get_manifest(ctx)
        self.min_driver = cfg.get("min_driver_version", 580)
        self.min_cuda = cfg.get("min_cuda_version", 13.0)
        self.index_url = cfg.get("index_url", "https://download.pytorch.org/whl/nightly/cu130")
        self.packages = cfg.get("packages", ["torch", "torchvision", "torchaudio"])

        logger.info(f"  -> 算力基线约束: Driver >= {self.min_driver}, CUDA >= {self.min_cuda}")
        logger.info(f"  -> 引擎包来源: {self.index_url}")

        # 2. 幂等性检查
        is_ready = self._is_torch_cuda_ready(ctx, self.min_cuda)
        cuda_info = self._get_torch_cuda_info(ctx)
        logger.debug(f"  -> [DEBUG] Torch 幂等检查: is_ready={is_ready}, cuda_info={cuda_info}")
        
        if is_ready:
            logger.info(f"  -> [SKIP] PyTorch (CUDA >= {self.min_cuda}) 已就绪，跳过安装。")
            ctx.artifacts.torch_installed = True
            return

        # 3. 真实的物理执行
        self._check_driver_version(ctx)
        self._install_torch(ctx)
        
        # 产出
        ctx.artifacts.torch_installed = True

    def _check_driver_version(self, ctx: AppContext) -> None:
        """校验 NVIDIA 驱动版本 (无卡模式下跳过)"""
        try:
            res = ctx.cmd.run(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                check=True,
            )
            version_str = res.stdout.strip().split('\n')[0]
            major_version = int(version_str.split('.')[0])
            
            logger.info(f"  -> 当前宿主机驱动版本: {version_str}")
            if major_version < self.min_driver:
                logger.error(f"  -> [ERROR] CUDA 环境不达标！需要驱动 >= {self.min_driver}")
                sys.exit(1)
        except FileNotFoundError:
            logger.info("  -> [INFO] 无卡模式，跳过驱动校验 (PyTorch 包仍会下载)")
        except Exception as e:
            logger.warning(f"  -> [WARN] 驱动校验异常，跳过严格限制: {e}")

    def _install_torch(self, ctx: AppContext) -> None:
        """通过 uv 安装 PyTorch CUDA 版本"""
        logger.info("  -> 正在调用 uv 极速对齐 Torch 算力引擎...")
        
        cmd = ["uv", "pip", "install", "--system", "--upgrade", "--pre"]
        cmd.extend(self.packages)
        cmd.extend(["--index-url", self.index_url])
        
        returncode = ctx.cmd.run_realtime(cmd)
        
        if returncode != 0:
            raise RuntimeError(f"Torch 安装失败，退出码: {returncode}, 命令: {' '.join(cmd)}")
        
        logger.info("  -> Torch 算力引擎对齐完成！")

    @hookimpl
    def start(self, context: AppContext) -> None:
        pass

    @hookimpl
    def sync(self, context: AppContext) -> None:
        pass
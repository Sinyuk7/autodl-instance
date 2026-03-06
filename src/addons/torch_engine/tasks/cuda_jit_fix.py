"""
CUDA JIT 依赖链修复 - NVRTC 版本

问题背景:
    PyTorch 2.x+cu13x 在 JIT 编译自定义 CUDA 算子时，依赖 CUDA 13.0 的 NVRTC
    (NVIDIA Runtime Compilation) 动态库。然而在 Conda 环境中，多版本 nvidia-*
    包的冲突会导致 torch/lib/ 下的 libnvrtc-builtins.so.13.0 变成死链接。
    
    症状:
    - RuntimeError: CUDA error: JIT compilation failed
    - failed to open libnvrtc-builtins.so.13.0
    - QwenVL 等需要 JIT 编译的模型推理失败
    
修复策略 (确定性逻辑):
    1. find -L + -type f: 过滤死链接，定位真实的 NVRTC 物理文件
    2. cp 至 /usr/lib/x86_64-linux-gnu/: 硬拷贝到系统最高优先级库目录
    3. ldconfig: 强制重建动态链接缓存
    4. 清理 torch_extensions 缓存: 移除错误的 JIT 编译中间产物
"""
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from src.core.interface import AppContext
from src.core.task import BaseTask, TaskResult
from src.core.utils import logger


# NVRTC 库文件名模式 (按优先级排序)
NVRTC_LIB_PATTERNS = [
    "libnvrtc-builtins.so.13.0",
    "libnvrtc-builtins.so.13",
    "libnvrtc-builtins.so.12.8",
    "libnvrtc-builtins.so.12",
]

# 系统级库目录 (dlopen fallback 最高优先级)
SYSTEM_LIB_DIR = Path("/usr/lib/x86_64-linux-gnu")


@dataclass
class FixCudaDependencyChainTask(BaseTask):
    """
    修复 CUDA JIT 依赖链 (NVRTC)
    
    针对 PyTorch JIT 编译时 NVRTC 库死链接问题，采用硬拷贝策略：
    1. 定位 Conda 环境中真实的 NVRTC 物理文件
    2. 硬拷贝到系统库目录
    3. 重建 ldconfig 缓存
    4. 清理 PyTorch JIT 编译缓存
    """
    
    name: str = "FixCudaDependencyChain"
    description: str = "修复 CUDA NVRTC 依赖链 (死链接问题)"
    priority: int = 5  # 在 Torch 安装之前执行
    
    # 幂等标记文件
    marker_file: Path = field(
        default_factory=lambda: Path("/tmp/.cuda_nvrtc_fixed")
    )
    
    def execute(self, ctx: AppContext) -> TaskResult:
        """
        执行 CUDA NVRTC 依赖链修复
        
        幂等性保证:
        - 检查标记文件是否存在
        - 检查系统库目录中是否已有完整的 NVRTC 文件
        - 仅在需要时执行修复
        """
        logger.info(f"  -> [Task] {self.name}: 检测 NVRTC 依赖链...")
        
        # Step 1: 幂等检查 - 标记文件
        if self.marker_file.exists():
            logger.info(f"  -> [Task] {self.name}: 已修复过 (标记文件存在)")
            return TaskResult.SKIPPED
        
        # Step 2: 幂等检查 - 系统库目录中是否已有完整文件
        existing_libs = self._check_system_libs()
        if existing_libs:
            logger.info(
                f"  -> [Task] {self.name}: 系统库目录已有 NVRTC 文件: "
                f"{[lib.name for lib in existing_libs]}"
            )
            self._create_marker()
            return TaskResult.SKIPPED
        
        # Step 3: 定位 Conda 环境中的真实 NVRTC 物理文件
        source_files = self._find_nvrtc_physical_files()
        if not source_files:
            logger.info(
                f"  -> [Task] {self.name}: 未找到 NVRTC 物理文件，跳过 "
                "(可能不需要此修复)"
            )
            return TaskResult.SKIPPED
        
        logger.info(
            f"  -> [Task] {self.name}: 发现 {len(source_files)} 个 NVRTC 物理文件"
        )
        
        # Step 4: 硬拷贝到系统库目录
        try:
            copied_count = self._copy_to_system_lib(source_files)
            if copied_count == 0:
                logger.warning(f"  -> [Task] {self.name}: 没有文件被拷贝")
                return TaskResult.SKIPPED
            
            # Step 5: 重建动态链接缓存
            self._run_ldconfig()
            
            # Step 6: 清理 PyTorch JIT 缓存
            self._clear_jit_cache()
            
            # Step 7: 创建幂等标记
            self._create_marker()
            
            logger.info(
                f"  -> [Task] {self.name}: ✓ 修复完成，已拷贝 {copied_count} 个文件"
            )
            return TaskResult.SUCCESS
            
        except PermissionError as e:
            logger.error(f"  -> [Task] {self.name}: 权限不足 - {e}")
            logger.info("  -> [Task] 提示: 请使用 root 权限运行，或手动执行修复")
            return TaskResult.FAILED
        except Exception as e:
            logger.error(f"  -> [Task] {self.name}: 修复失败 - {e}")
            return TaskResult.FAILED
    
    def _check_system_libs(self) -> List[Path]:
        """
        检查系统库目录中是否已有 NVRTC 文件
        
        Returns:
            已存在的 NVRTC 库文件列表
        """
        if not SYSTEM_LIB_DIR.exists():
            return []
        
        existing = []
        for pattern in NVRTC_LIB_PATTERNS:
            lib_path = SYSTEM_LIB_DIR / pattern
            # 必须是真实文件且大小 > 0
            if lib_path.exists() and lib_path.is_file() and lib_path.stat().st_size > 0:
                existing.append(lib_path)
        return existing
    
    def _find_nvrtc_physical_files(self) -> List[Path]:
        """
        定位 Conda 环境中真实的 NVRTC 物理文件
        
        使用 find -L ... -type f 策略:
        - -L: 跟随符号链接
        - -type f: 仅限普通文件 (过滤死链接)
        
        搜索路径优先级:
        1. CONDA_PREFIX/lib/python*/site-packages/nvidia/cuda_nvrtc/lib/
        2. CONDA_PREFIX/lib/
        3. sys.prefix (virtualenv)
        
        Returns:
            真实 NVRTC 物理文件路径列表 (去重，按优先级排序)
        """
        search_roots: List[Path] = []
        
        # Conda 环境
        conda_prefix = os.environ.get("CONDA_PREFIX")
        if conda_prefix:
            conda_path = Path(conda_prefix)
            # nvidia 包的标准安装位置
            for site_pkg in conda_path.glob("lib/python*/site-packages"):
                nvrtc_lib = site_pkg / "nvidia" / "cuda_nvrtc" / "lib"
                if nvrtc_lib.exists():
                    search_roots.append(nvrtc_lib)
            # Conda lib 目录
            search_roots.append(conda_path / "lib")
        
        # 虚拟环境
        import sys
        venv_path = Path(sys.prefix)
        if venv_path != Path("/usr"):
            for site_pkg in venv_path.glob("lib/python*/site-packages"):
                nvrtc_lib = site_pkg / "nvidia" / "cuda_nvrtc" / "lib"
                if nvrtc_lib.exists():
                    search_roots.append(nvrtc_lib)
        
        # 使用 find 命令搜索 (更可靠地过滤死链接)
        found_files: List[Path] = []
        seen_names: set = set()
        
        for search_root in search_roots:
            if not search_root.exists():
                continue
            
            for pattern in NVRTC_LIB_PATTERNS:
                try:
                    # find -L <path> -name <pattern> -type f
                    # -L: 跟随符号链接
                    # -type f: 仅限普通文件
                    result = subprocess.run(
                        ["find", "-L", str(search_root), "-name", pattern, "-type", "f"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    for line in result.stdout.strip().split("\n"):
                        if not line:
                            continue
                        file_path = Path(line)
                        # 验证文件存在且大小 > 0
                        if (
                            file_path.exists() 
                            and file_path.is_file() 
                            and file_path.stat().st_size > 0
                            and file_path.name not in seen_names
                        ):
                            found_files.append(file_path)
                            seen_names.add(file_path.name)
                            logger.info(
                                f"  -> [Task] {self.name}: 发现物理文件 "
                                f"{file_path} ({file_path.stat().st_size} bytes)"
                            )
                            
                except subprocess.TimeoutExpired:
                    logger.warning(f"  -> [Task] {self.name}: find 命令超时: {search_root}")
                except Exception as e:
                    logger.warning(f"  -> [Task] {self.name}: 搜索失败 {search_root}: {e}")
        
        return found_files
    
    def _copy_to_system_lib(self, source_files: List[Path]) -> int:
        """
        硬拷贝 NVRTC 文件到系统库目录
        
        策略:
        - 使用 cp (不是软链接) 确保 dlopen fallback 能找到
        - 保留文件权限和时间戳
        
        Args:
            source_files: 源文件路径列表
            
        Returns:
            成功拷贝的文件数量
        """
        if not SYSTEM_LIB_DIR.exists():
            logger.warning(
                f"  -> [Task] {self.name}: 系统库目录不存在 {SYSTEM_LIB_DIR}"
            )
            return 0
        
        copied = 0
        for src in source_files:
            dst = SYSTEM_LIB_DIR / src.name
            
            # 检查目标文件是否已存在且完整
            if dst.exists() and dst.is_file():
                src_size = src.stat().st_size
                dst_size = dst.stat().st_size
                if dst_size == src_size:
                    logger.info(
                        f"  -> [Task] {self.name}: 跳过 {src.name} "
                        f"(目标已存在且大小一致)"
                    )
                    continue
            
            try:
                # 硬拷贝 (保留权限)
                shutil.copy2(src, dst)
                logger.info(f"  -> [Task] {self.name}: 已拷贝 {src.name} -> {dst}")
                copied += 1
            except Exception as e:
                logger.error(f"  -> [Task] {self.name}: 拷贝失败 {src.name}: {e}")
        
        return copied
    
    def _run_ldconfig(self) -> None:
        """
        运行 ldconfig 重建动态链接缓存
        
        这是修复的关键步骤，确保新拷贝的库文件立即生效
        """
        try:
            subprocess.run(
                ["ldconfig"],
                check=True,
                capture_output=True,
                timeout=60
            )
            logger.info(f"  -> [Task] {self.name}: 已重建 ldconfig 缓存")
        except subprocess.CalledProcessError as e:
            logger.warning(
                f"  -> [Task] {self.name}: ldconfig 失败 (可能需要 root 权限): "
                f"{e.stderr.decode() if e.stderr else e}"
            )
        except FileNotFoundError:
            logger.warning(f"  -> [Task] {self.name}: ldconfig 命令不存在")
        except Exception as e:
            logger.warning(f"  -> [Task] {self.name}: ldconfig 执行异常: {e}")
    
    def _clear_jit_cache(self) -> None:
        """
        清理 PyTorch JIT 编译缓存
        
        关键: 必须清除 torch_extensions 目录，否则 PyTorch JIT 会读取
        之前因链接失败而生成的错误编译中间产物，不会触发重新编译
        """
        cache_dirs = [
            Path.home() / ".cache" / "torch_extensions",  # 主要目标
            Path.home() / ".cache" / "torch" / "kernels",
        ]
        
        for cache_dir in cache_dirs:
            if cache_dir.exists():
                try:
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    logger.info(f"  -> [Task] {self.name}: 已清理 JIT 缓存 {cache_dir}")
                except Exception as e:
                    logger.warning(
                        f"  -> [Task] {self.name}: 清理缓存失败 {cache_dir}: {e}"
                    )
    
    def _create_marker(self) -> None:
        """创建幂等标记文件"""
        try:
            self.marker_file.parent.mkdir(parents=True, exist_ok=True)
            self.marker_file.touch()
        except Exception as e:
            # 标记文件创建失败不影响主流程
            logger.warning(f"  -> [Task] {self.name}: 创建标记文件失败: {e}")

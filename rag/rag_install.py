#!/usr/bin/env python3
"""
RAG 本地检索系统 - 安装/初始化脚本

使用方法:
    # 方式 1: 下载并运行
    curl -sSL https://raw.githubusercontent.com/your-repo/rag-install.py | python3
    
    # 方式 2: 本地运行
    python3 rag_install.py
    
    # 方式 3: 指定目标目录
    python3 rag_install.py /path/to/your/project

功能:
    1. 检查/创建 conda 环境 (rag-env, Python 3.11)
    2. 安装依赖 (sentence-transformers, numpy)
    3. 复制 RAG 核心代码到目标项目
    4. 创建启动脚本
    5. 更新 .gitignore
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

# ============================================================
# 安装逻辑
# ============================================================

def run_cmd(cmd, check=True, capture=False):
    """运行命令"""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if check and result.returncode != 0:
        print(f"  ❌ 命令失败: {result.stderr if capture else ''}")
        return None
    return result

def check_conda():
    """检查 conda 是否安装"""
    result = subprocess.run(["which", "conda"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    
    # 检查 miniforge
    miniforge_path = "/usr/local/Caskroom/miniforge/base/bin/conda"
    if os.path.exists(miniforge_path):
        return miniforge_path
    
    return None

def setup_conda_env():
    """设置 conda 环境"""
    conda_path = check_conda()
    
    if not conda_path:
        print("\n❌ 未找到 conda，请先安装 miniforge:")
        print("   brew install --cask miniforge")
        print("   然后重新运行此脚本")
        return False
    
    print(f"\n✅ 找到 conda: {conda_path}")
    
    # 检查 rag-env 是否存在
    result = subprocess.run(
        [conda_path, "env", "list"],
        capture_output=True, text=True
    )
    
    if "rag-env" in result.stdout:
        print("✅ rag-env 环境已存在")
    else:
        print("\n📦 创建 rag-env 环境 (Python 3.11)...")
        subprocess.run([conda_path, "create", "-n", "rag-env", "python=3.11", "-y"])
    
    # 安装依赖
    env_python = "/usr/local/Caskroom/miniforge/base/envs/rag-env/bin/pip"
    if os.path.exists(env_python):
        print("\n📦 安装依赖...")
        subprocess.run([env_python, "install", "sentence-transformers", "numpy", "-q"])
        print("✅ 依赖安装完成")
    
    return True

def install_rag_files(target_dir: Path):
    """配置 RAG 环境并生成启动脚本"""
    target_dir = Path(target_dir).resolve()
    source_dir = Path(__file__).parent.resolve()
    
    print(f"\n📁 配置 RAG 环境，项目根目录: {target_dir}")
    
    # 计算 rag 目录相对于项目根目录的路径
    try:
        rel_rag_dir = source_dir.relative_to(target_dir)
        rag_script_path = f"$PROJECT_ROOT/{rel_rag_dir}/rag_search.py"
    except ValueError:
        # 如果 rag 目录不在项目根目录下，使用绝对路径
        rag_script_path = str(source_dir / "rag_search.py")
    
    # 动态生成启动脚本
    launcher_content = f'''#!/bin/bash
# RAG 本地检索工具
PROJECT_ROOT="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

# 尝试寻找 conda
if command -v conda &> /dev/null; then
    CONDA_CMD="conda"
elif [ -f "/usr/local/Caskroom/miniforge/base/bin/conda" ]; then
    CONDA_CMD="/usr/local/Caskroom/miniforge/base/bin/conda"
elif [ -f "$HOME/miniforge3/bin/conda" ]; then
    CONDA_CMD="$HOME/miniforge3/bin/conda"
elif [ -f "$HOME/miniconda3/bin/conda" ]; then
    CONDA_CMD="$HOME/miniconda3/bin/conda"
else
    echo "❌ 未找到 conda 命令，请确保已安装 conda/miniforge"
    exit 1
fi

cd "$PROJECT_ROOT"
# 使用 conda run 执行，指向正确的 rag_search.py 路径
exec "$CONDA_CMD" run -n rag-env python "{rag_script_path}" "$@"
'''
    
    # 创建启动脚本
    launcher_path = target_dir / "rag_search"
    launcher_path.write_text(launcher_content)
    os.chmod(launcher_path, 0o755)
    print("  ✅ 创建: rag_search (启动脚本)")
    
    # 更新 .gitignore
    gitignore = target_dir / ".gitignore"
    ignore_entries = [
        ".rag_index/",
        "rag/__pycache__/"
    ]
    
    if gitignore.exists():
        content = gitignore.read_text()
        added_any = False
        with open(gitignore, "a") as f:
            for entry in ignore_entries:
                if entry not in content:
                    if not added_any:
                        f.write("\n# RAG 索引与缓存\n")
                        added_any = True
                    f.write(f"{entry}\n")
        if added_any:
            print("  ✅ 更新: .gitignore (添加 RAG 忽略项)")
    else:
        with open(gitignore, "w") as f:
            f.write("# RAG 索引与缓存\n")
            for entry in ignore_entries:
                f.write(f"{entry}\n")
        print("  ✅ 创建: .gitignore")

def main():
    print("=" * 60)
    print("🚀 RAG 本地检索系统 - 安装程序")
    print("=" * 60)
    
    # 确定目标目录
    if len(sys.argv) > 1:
        target_dir = Path(sys.argv[1])
    else:
        target_dir = Path.cwd()
    
    print(f"\n目标目录: {target_dir}")
    
    # 1. 设置 conda 环境
    if not setup_conda_env():
        sys.exit(1)
    
    # 2. 安装文件
    install_rag_files(target_dir)
    
    # 完成
    print("\n" + "=" * 60)
    print("✅ 安装完成！")
    print("=" * 60)
    print("\n使用方法:")
    print(f"  cd {target_dir}")
    print("  ./rag_search")
    print("\n首次运行会自动构建索引（约 1-2 分钟）")
    print("之后使用 'update' 命令进行增量更新")
    print("=" * 60)

if __name__ == "__main__":
    main()

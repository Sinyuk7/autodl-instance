#!/usr/bin/env python3
import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 确保 autodl_setup logger 有 handler（独立 CLI 运行时未经 main.py 初始化）
logging.basicConfig(level=logging.INFO, format="%(message)s")

# 初始化网络环境 (加载代理、镜像、API Token)
from src.lib.network import setup_network
setup_network(verbose=True)

# 导入核心模块
from src.lib.download import (
    download_model as core_download,
    extract_filename_from_url,
    cache_info,
    purge_cache,
)
from src.lib.download.civitai import resolve_civitai_url
from src.lib.download.url_utils import detect_url_type
from src.lib import ui
from src.lib.utils import load_yaml, format_size

# 导入本地模块
from src.addons.models.config import (
    PRESETS_FILE,
    get_models_base,
    get_type_dir_mapping,
    resolve_type_to_dir,
    LOCK_FILE,
)
from src.addons.models.lock import write_meta
from src.addons.models.schema import PresetsFile


def load_presets() -> PresetsFile:
    """加载并验证 manifest.yaml，配置有误时立即报错"""
    from pydantic import ValidationError
    raw = load_yaml(PRESETS_FILE)
    try:
        return PresetsFile.model_validate(raw)
    except ValidationError as e:
        ui.print_error(f"manifest.yaml 配置有误:\n{e}")
        sys.exit(1)


# ============================================================
# CLI 命令 - list
# ============================================================
def cmd_list() -> None:
    """列出已下载模型 (使用 Rich 美化)"""
    base = get_models_base()
    ui.print_panel("模型目录", str(base))
    
    if not base.exists():
        ui.print_warning("目录不存在")
        return
    
    # 收集模型文件 (排除法: 跳过隐藏文件和已知非模型扩展名)
    from src.addons.models.lock import EXCLUDED_EXTENSIONS
    model_files: List[Path] = []
    for f in base.rglob("*"):
        if not f.is_file():
            continue
        if f.name.startswith("."):
            continue
        if f.suffix.lower() in EXCLUDED_EXTENSIONS:
            continue
        model_files.append(f)
    
    if not model_files:
        ui.print_info("暂无模型文件")
        return
    
    # 按目录分组显示
    rows: List[List[str]] = []
    for f in sorted(model_files):
        rel_path = f.relative_to(base)
        size = f.stat().st_size // 1024  # KB
        rows.append([str(rel_path), format_size(size)])
    
    ui.print_table(
        title=f"模型文件 ({len(model_files)} 个)",
        columns=["路径", "大小"],
        rows=rows,
    )


# ============================================================
# CLI 命令 - status
# ============================================================
def cmd_status() -> None:
    """显示 lock 文件中的记录 (使用 Rich 美化)"""
    lock = load_yaml(LOCK_FILE)
    models = lock.get("models", [])
    
    if not models:
        ui.print_info("暂无模型记录 (model_lock.yaml)")
        return
    
    base = get_models_base()
    rows: List[List[str]] = []
    
    for m in models:
        name = m.get("model", "?")
        mtype = m.get("type", "?")
        path = m.get("paths", [{}])[0].get("path", "")
        exists = (base / path).exists() if path else False
        status = "[green]✓[/green]" if exists else "[red]✗[/red]"
        rows.append([status, name, mtype, path])
    
    ui.print_table(
        title=f"模型记录 ({len(models)} 个)",
        columns=["状态", "名称", "类型", "路径"],
        rows=rows,
    )


# ============================================================
# CLI 命令 - types
# ============================================================
def cmd_types() -> None:
    """显示可用的模型类型 (使用 Rich 美化)"""
    mapping = get_type_dir_mapping()
    
    rows: List[List[str]] = []
    for mtype, mdir in sorted(mapping.items()):
        rows.append([mtype, mdir])
    
    ui.print_table(
        title="可用模型类型",
        columns=["类型名", "目标目录"],
        rows=rows,
    )
    
    ui.print_info("也可以直接使用子目录路径，如: clip/flux, unet/flux")


# ============================================================
# CLI 命令 - download (交互式)
# ============================================================
def _write_download_meta(
    target_path: Path,
    url: str,
    source: str,
    model_name: Optional[str] = None,
    extra_info: Optional[Dict[str, Any]] = None,
) -> None:
    """下载完成后写入 .meta sidecar
    
    Args:
        target_path: 模型文件路径
        url: 原始下载 URL
        source: 来源类型 (civitai, huggingface, preset, direct)
        model_name: 模型名称 (可选)
        extra_info: 额外信息字典 (如 CivitAI API 返回的信息)
    """
    from datetime import datetime, timezone
    meta = {
        "url": url,
        "source": source,
        "model": model_name or target_path.stem,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    
    # 合并额外信息 (如 CivitAI 的 model_type, base_model, size_kb 等)
    if extra_info:
        # 避免覆盖核心字段
        for key, value in extra_info.items():
            if key not in meta and value is not None:
                meta[key] = value
    
    write_meta(target_path, meta)


def cmd_download_interactive(url: str) -> None:
    """交互式下载单个模型"""
    base = get_models_base()
    url_type = detect_url_type(url)
    
    # 用于存储解析结果
    filename: str = ""
    suggested_type: Optional[str] = None
    suggested_subdir: Optional[str] = None
    download_url: str = url
    size_info: str = ""
    civitai_info: Optional[Dict[str, Any]] = None  # 保存 CivitAI API 返回的完整信息
    
    ui.print_panel("下载模型", f"URL: {url}\n来源: {url_type.upper()}")
    
    # ========== Step 1: 解析 URL 获取信息 ==========
    if url_type == "civitai":
        ui.print_info("正在解析 CivitAI 模型信息...")
        resolved_url, info = resolve_civitai_url(url)
        
        if info:
            civitai_info = info  # 保存完整信息用于写入 .meta
            filename = info.get("filename", "")
            suggested_type = info.get("comfy_type", "")
            suggested_subdir = info.get("base_model", "")
            download_url = resolved_url or url
            size_kb = info.get("size_kb", 0)
            if size_kb:
                size_info = format_size(size_kb)
            
            ui.print_success(f"解析成功: {filename}")
            ui.print_info(f"类型: {info.get('model_type', '?')} → {suggested_type}")
            ui.print_info(f"基底模型: {suggested_subdir}")
            if size_info:
                ui.print_info(f"文件大小: {size_info}")
        else:
            ui.print_warning("无法解析 CivitAI 信息，将使用直链下载")
            filename = extract_filename_from_url(url)
    
    elif url_type == "huggingface":
        filename = extract_filename_from_url(url)
        # 尝试从路径推断类型 (如 .../unet/... -> unet)
        url_lower = url.lower()
        for known_type in ["unet", "clip", "vae", "lora", "controlnet", "checkpoints"]:
            if f"/{known_type}/" in url_lower or f"/{known_type}s/" in url_lower:
                suggested_type = known_type
                break
    else:
        filename = extract_filename_from_url(url)
    
    # ========== Step 2: 确认/修改文件名 ==========
    if not filename:
        filename = ui.prompt_input("请输入文件名", default="model.safetensors")
    else:
        new_filename = ui.prompt_input("文件名", default=filename)
        if new_filename:
            filename = new_filename
    
    # ========== Step 3: 选择模型类型 ==========
    available_types = list(get_type_dir_mapping().keys())
    
    if suggested_type and suggested_type in available_types:
        # 有推荐类型，让用户确认
        use_suggested = ui.prompt_confirm(
            f"检测到类型: {suggested_type}，是否使用？",
            default=True
        )
        if use_suggested:
            final_type = suggested_type
        else:
            final_type = ui.prompt_select("选择模型类型", available_types)
    else:
        # 无推荐，让用户选择
        final_type = ui.prompt_select("选择模型类型", available_types)
    
    # ========== Step 4: 确定子目录 ==========
    base_dir = resolve_type_to_dir(final_type)
    
    if suggested_subdir:
        # 有推荐子目录 (如 SDXL, Pony)
        use_subdir = ui.prompt_confirm(
            f"是否放入子目录 '{suggested_subdir}'？",
            default=True
        )
        if use_subdir:
            rel_dir = f"{base_dir}/{suggested_subdir}"
        else:
            custom = ui.prompt_input("自定义子目录 (留空则不使用)", default="")
            rel_dir = f"{base_dir}/{custom}" if custom else base_dir
    else:
        custom = ui.prompt_input("子目录 (留空则直接放入类型目录)", default="")
        rel_dir = f"{base_dir}/{custom}" if custom else base_dir
    
    target_dir = base / rel_dir
    target_path = target_dir / filename
    
    # ========== Step 5: 处理文件已存在 ==========
    if target_path.exists():
        ui.print_warning(f"文件已存在: {target_path}")
        
        choice = ui.prompt_choice(
            "请选择操作",
            ["覆盖", "重命名", "跳过"],
            default="跳过"
        )
        
        if choice == "跳过":
            ui.print_info("已跳过")
            return
        elif choice == "重命名":
            stem = target_path.stem
            suffix = target_path.suffix
            new_name = ui.prompt_input(
                "新文件名",
                default=f"{stem}_new{suffix}"
            )
            filename = new_name
            target_path = target_dir / filename
        # choice == "覆盖" 则继续
    
    # ========== Step 6: 确认下载 ==========
    rel_path = f"{rel_dir}/{filename}"
    
    ui.console.print("")
    ui.print_panel(
        "下载确认",
        f"文件名: {filename}\n"
        f"目标: {target_path}\n"
        f"相对路径: {rel_path}"
        + (f"\n预计大小: {size_info}" if size_info else ""),
        style="green"
    )
    
    if not ui.prompt_confirm("开始下载？", default=True):
        ui.print_info("已取消")
        return
    
    # ========== Step 7: 执行下载 ==========
    target_dir.mkdir(parents=True, exist_ok=True)
    
    ui.print_info("正在下载...")
    
    if not core_download(download_url, target_path):
        ui.print_error("下载失败")
        sys.exit(1)
    
    # ========== Step 8: 写入 .meta sidecar ==========
    _write_download_meta(target_path, url=url, source=url_type, extra_info=civitai_info)
    
    ui.print_success(f"下载完成: {rel_path}")


# ============================================================
# CLI 命令 - download preset (批量)
# ============================================================
def cmd_download_preset(preset_name: str) -> None:
    """下载指定预设的所有模型"""
    # 加载并验证预设文件（配置有误时在此处立即报错）
    presets_file = load_presets()
    presets = presets_file.presets

    # 大小写不敏感匹配
    matched_name: Optional[str] = None
    if preset_name in presets:
        matched_name = preset_name
    else:
        preset_lower = preset_name.lower()
        for key in presets.keys():
            if key.lower() == preset_lower:
                matched_name = key
                break

    if not matched_name:
        ui.print_error(f"未找到预设: {preset_name}")
        ui.print_info(f"可用预设: {', '.join(presets.keys())}")
        sys.exit(1)

    preset = presets[matched_name]
    base = get_models_base()

    ui.print_panel(
        f"预设: {matched_name}",
        f"描述: {preset.description or 'N/A'}\n模型数: {len(preset.models)}"
    )

    success_count = 0
    fail_count = 0
    skip_count = 0

    for entry in preset.models:
        name = entry.model
        rel_path = entry.primary_path
        target = base / rel_path

        # 幂等性检查：以本地文件是否存在为准
        if target.exists():
            ui.print_info(f"[{name}] 已存在，跳过")
            skip_count += 1
            continue

        target.parent.mkdir(parents=True, exist_ok=True)

        ui.console.print(f"\n[bold blue]>>> 下载 {name}[/bold blue]")

        if core_download(entry.url, target):
            if target.exists():
                # 写入 .meta sidecar（不动 model-lock.yaml）
                _write_download_meta(target, url=entry.url, source="preset",
                                     model_name=name)
                ui.print_success(f"[{name}] 完成")
                success_count += 1
            else:
                ui.print_error(f"[{name}] 下载后文件未找到")
                fail_count += 1
        else:
            ui.print_error(f"[{name}] 下载失败")
            fail_count += 1

    ui.console.print("")
    ui.print_panel(
        "下载完成",
        f"成功: {success_count}\n失败: {fail_count}\n跳过: {skip_count}",
        style="green" if fail_count == 0 else "yellow"
    )


# ============================================================
# CLI 命令 - cache (缓存管理)
# ============================================================
def cmd_cache_list() -> None:
    """列出所有下载缓存"""
    entries = cache_info()

    rows: List[List[str]] = []
    total_size = 0

    for entry in entries:
        if entry.exists:
            total_size += entry.size_bytes
            size_str = format_size(entry.size_bytes // 1024)
            status = "[green]存在[/green]"
        else:
            size_str = "-"
            status = "[dim]不存在[/dim]"
        rows.append([entry.name, str(entry.path), size_str, status])

    ui.print_table(
        title="下载缓存",
        columns=["名称", "路径", "大小", "状态"],
        rows=rows,
    )

    if total_size > 0:
        ui.print_info(f"缓存总大小: {format_size(total_size // 1024)}")


def cmd_cache_clear(force: bool = False) -> None:
    """清理下载缓存"""
    ui.print_panel("清理缓存", "范围: 全部")

    if not force:
        ui.print_warning("此操作将删除下载缓存，已下载完成的模型不受影响。")
        if not ui.prompt_confirm("确认清理？", default=False):
            ui.print_info("已取消")
            return

    results = purge_cache()

    if not results:
        ui.print_info("没有需要清理的缓存")
        return

    total_cleared = 0
    for result in results:
        if result.success:
            total_cleared += result.freed_bytes
            size_str = format_size(result.freed_bytes // 1024) if result.freed_bytes > 0 else "0"
            ui.print_success(f"已清理: {result.path} ({size_str})")
        else:
            ui.print_warning(f"清理失败: {result.path}" + (f" ({result.error})" if result.error else ""))

    if total_cleared > 0:
        ui.console.print("")
        ui.print_success(f"共释放空间: {format_size(total_cleared // 1024)}")


# ============================================================
# 入口
# ============================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="ComfyUI 模型管理器 (交互式)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
下载策略:
  - 所有 URL 类型统一使用 aria2c 多线程下载

环境变量:
  HF_TOKEN           HuggingFace API Token
  CIVITAI_API_TOKEN  CivitAI API Token

示例:
  model download https://huggingface.co/.../model.safetensors
  model download https://civitai.com/models/12345
  model download -p FLUX.2-klein-9B

  model list                       # 列出模型文件
  model status                     # 查看快照记录
  model types                      # 显示可用模型类型

缓存管理:
  model cache                      # 查看下载缓存
  model cache clear                # 清理所有缓存
        """
    )
    sub = parser.add_subparsers(dest="cmd")
    
    sub.add_parser("list", help="列出已下载模型")
    sub.add_parser("status", help="查看 lock 记录")
    sub.add_parser("types", help="显示可用模型类型")
    
    dl = sub.add_parser("download", help="下载模型 (交互式)")
    dl.add_argument("url", nargs="?", help="模型 URL (HuggingFace, CivitAI, 直链)")
    dl.add_argument("-p", "--preset", help="预设名称 (见 manifest.yaml)")
    
    # 缓存管理子命令
    cache_parser = sub.add_parser("cache", help="缓存管理")
    cache_sub = cache_parser.add_subparsers(dest="cache_cmd")
    
    cache_sub.add_parser("list", help="列出下载缓存")
    
    cache_clear = cache_sub.add_parser("clear", help="清理下载缓存")
    cache_clear.add_argument("-f", "--force", action="store_true", help="跳过确认")
    
    args = parser.parse_args()
    
    if args.cmd == "list":
        cmd_list()
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "types":
        cmd_types()
    elif args.cmd == "download":
        if args.preset:
            cmd_download_preset(args.preset)
        elif args.url:
            cmd_download_interactive(args.url)
        else:
            ui.print_error("请提供 URL 或 --preset 参数")
            dl.print_help()
            sys.exit(1)
    elif args.cmd == "cache":
        if args.cache_cmd == "list" or args.cache_cmd is None:
            cmd_cache_list()
        elif args.cache_cmd == "clear":
            cmd_cache_clear(force=args.force)
        else:
            cache_parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
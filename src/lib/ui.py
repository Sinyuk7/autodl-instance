"""
交互式 UI 工具模块

基于 prompt_toolkit 和 rich 实现友好的命令行交互
"""
from typing import Dict, List, Optional

from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.validation import Validator
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn


console = Console()


# ============================================================
# 输入交互
# ============================================================
def prompt_input(
    message: str,
    default: str = "",
    completer_words: Optional[List[str]] = None,
    validator: Optional[Validator] = None,
) -> str:
    """带自动补全的输入提示
    
    Args:
        message: 提示信息
        default: 默认值
        completer_words: 自动补全候选词
        validator: 输入验证器
        
    Returns:
        用户输入的字符串
    """
    completer = WordCompleter(completer_words) if completer_words else None
    
    suffix = f" [{default}]" if default else ""
    result = prompt(
        f"{message}{suffix}: ",
        default=default,
        completer=completer,
        validator=validator,
    )
    return result.strip() or default


def prompt_confirm(message: str, default: bool = True) -> bool:
    """确认提示 (y/n)
    
    Args:
        message: 提示信息
        default: 默认值
        
    Returns:
        True/False
    """
    hint = "[Y/n]" if default else "[y/N]"
    result = prompt(f"{message} {hint}: ").strip().lower()
    
    if not result:
        return default
    return result in ("y", "yes", "是", "确认")


def prompt_select(
    message: str,
    options: List[str],
    default_index: int = 0,
) -> str:
    """单选菜单
    
    Args:
        message: 提示信息
        options: 选项列表
        default_index: 默认选中的索引
        
    Returns:
        选中的选项字符串
    """
    console.print(f"\n[bold cyan]{message}[/bold cyan]")
    
    for i, opt in enumerate(options):
        marker = "→" if i == default_index else " "
        console.print(f"  {marker} [{i + 1}] {opt}")
    
    default_num = str(default_index + 1)
    result = prompt(f"请选择 [{default_num}]: ").strip()
    
    if not result:
        return options[default_index]
    
    try:
        idx = int(result) - 1
        if 0 <= idx < len(options):
            return options[idx]
    except ValueError:
        # 尝试匹配选项内容
        for opt in options:
            if result.lower() in opt.lower():
                return opt
    
    return options[default_index]


def prompt_choice(
    message: str,
    choices: List[str],
    default: Optional[str] = None,
) -> str:
    """快速选择 (输入首字母或数字)
    
    示例: prompt_choice("文件已存在", ["覆盖", "重命名", "跳过"])
    
    Args:
        message: 提示信息
        choices: 选项列表
        default: 默认选项
        
    Returns:
        选中的选项
    """
    # 构建显示和快捷键映射
    display_parts: List[str] = []
    key_map: Dict[str, str] = {}
    
    for i, choice in enumerate(choices):
        key = str(i + 1)
        key_map[key] = choice
        # 也支持首字母
        first_char = choice[0].lower()
        if first_char not in key_map:
            key_map[first_char] = choice
        
        if default and choice == default:
            display_parts.append(f"[{key}] {choice} (默认)")
        else:
            display_parts.append(f"[{key}] {choice}")
    
    console.print(f"[bold yellow]{message}[/bold yellow]")
    console.print("  " + "  ".join(display_parts))
    
    result = prompt("请选择: ").strip().lower()
    
    if not result and default:
        return default
    
    return key_map.get(result, default or choices[0])


# ============================================================
# 输出美化
# ============================================================
def print_info(message: str) -> None:
    """打印信息"""
    console.print(f"[cyan]ℹ[/cyan] {message}")


def print_success(message: str) -> None:
    """打印成功信息"""
    console.print(f"[green]✓[/green] {message}")


def print_warning(message: str) -> None:
    """打印警告信息"""
    console.print(f"[yellow]⚠[/yellow] {message}")


def print_error(message: str) -> None:
    """打印错误信息"""
    console.print(f"[red]✗[/red] {message}")


def print_panel(title: str, content: str, style: str = "blue") -> None:
    """打印面板"""
    console.print(Panel(content, title=title, border_style=style))


def print_table(
    title: str,
    columns: List[str],
    rows: List[List[str]],
) -> None:
    """打印表格
    
    Args:
        title: 表格标题
        columns: 列名列表
        rows: 行数据列表
    """
    table = Table(title=title, show_header=True, header_style="bold magenta")
    
    for col in columns:
        table.add_column(col)
    
    for row in rows:
        table.add_row(*row)
    
    console.print(table)


# ============================================================
# 进度条
# ============================================================
def create_download_progress() -> Progress:
    """创建下载进度条"""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

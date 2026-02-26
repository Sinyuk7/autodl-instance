"""
Artifacts - 插件间共享的强类型数据容器

支持持久化到 JSON 文件，实现跨进程共享（setup → start → sync）。
"""
import json
from dataclasses import dataclass, fields, asdict
from pathlib import Path
from typing import Optional, Any, Dict


ARTIFACTS_FILENAME = ".artifacts.json"


@dataclass
class Artifacts:
    """
    插件产出的强类型容器。
    
    这是一个纯数据对象（DTO），新增插件时需要在此添加对应字段。
    这是有意的设计，目的是：
    - 强制声明插件的输入输出契约
    - 编译时类型检查
    - IDE 自动补全
    
    支持持久化：
    - save(path): 保存到 JSON 文件
    - load(path): 从 JSON 文件加载
    """
    
    # ==================== ComfyAddon ====================
    comfy_dir: Optional[Path] = None
    custom_nodes_dir: Optional[Path] = None
    user_dir: Optional[Path] = None
    
    # ==================== NodesAddon ====================
    snapshots_dir: Optional[Path] = None
    latest_snapshot: Optional[Path] = None
    
    # ==================== UserdataAddon ====================
    userdata_dir: Optional[Path] = None
    
    # ==================== ModelAddon ====================
    models_dir: Optional[Path] = None
    extra_model_paths_file: Optional[Path] = None
    
    # ==================== SystemAddon ====================
    bin_dir: Optional[Path] = None
    ssh_dir: Optional[Path] = None
    uv_bin: Optional[Path] = None
    
    # ==================== TorchAddon ====================
    torch_installed: bool = False
    cuda_version: Optional[str] = None

    def save(self, project_root: Path) -> None:
        """
        保存 artifacts 到 JSON 文件。
        
        Args:
            project_root: 项目根目录，文件将保存为 {project_root}/.artifacts.json
        """
        file_path = project_root / ARTIFACTS_FILENAME
        data: Dict[str, Any] = {}
        
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, Path):
                data[field.name] = str(value)
            else:
                data[field.name] = value
        
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, project_root: Path) -> "Artifacts":
        """
        从 JSON 文件加载 artifacts。
        
        Args:
            project_root: 项目根目录
            
        Returns:
            加载的 Artifacts 实例，如果文件不存在则返回空实例
        """
        file_path = project_root / ARTIFACTS_FILENAME
        
        if not file_path.exists():
            return cls()
        
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return cls()
        
        # 获取所有字段的类型信息
        field_types = {f.name: f.type for f in fields(cls)}
        
        kwargs: Dict[str, Any] = {}
        for field_name, value in data.items():
            if field_name not in field_types:
                continue  # 忽略未知字段（兼容性）
            
            field_type = field_types[field_name]
            
            # 处理 Optional[Path] 类型
            if value is not None and "Path" in str(field_type):
                kwargs[field_name] = Path(value)
            else:
                kwargs[field_name] = value
        
        return cls(**kwargs)
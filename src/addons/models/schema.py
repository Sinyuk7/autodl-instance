"""
Models Addon - 配置 Schema 定义

为 manifest.yaml 提供 Pydantic 类型验证。
在 CLI 命令执行前即可发现预设配置错误，而不是在下载中途才报错。
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, field_validator


class ModelPath(BaseModel):
    """模型在共享目录中的存放路径"""
    path: str  # 相对于 shared_models/ 的路径，如 "unet/flux-2-klein-9b.safetensors"


class ModelEntry(BaseModel):
    """预设中的单个模型条目"""
    model: str               # 模型唯一标识名
    url: str                 # 下载 URL（支持 HuggingFace / CivitAI / 直链）
    paths: List[ModelPath]   # 存放路径列表（通常只有一个）
    type: Optional[str] = None  # 模型类型（可选标签，path 是真相，type 是注释）

    @field_validator("paths")
    @classmethod
    def paths_not_empty(cls, v: List[ModelPath]) -> List[ModelPath]:
        if not v:
            raise ValueError("paths 不能为空，至少需要一个存放路径")
        return v

    @property
    def primary_path(self) -> str:
        """获取主存放路径（第一个）"""
        return self.paths[0].path


class ModelPreset(BaseModel):
    """单个预设（一个工作流所需的所有模型组合）"""
    description: Optional[str] = None
    models: List[ModelEntry]

    @field_validator("models")
    @classmethod
    def models_not_empty(cls, v: List[ModelEntry]) -> List[ModelEntry]:
        if not v:
            raise ValueError("预设中至少需要声明一个模型")
        return v


class PresetsFile(BaseModel):
    """manifest.yaml 的顶层结构"""
    presets: Dict[str, ModelPreset] = {}

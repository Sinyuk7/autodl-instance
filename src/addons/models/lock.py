"""
Lock 文件管理

管理 model_lock.yaml 中的模型记录
"""
from typing import Any, Dict, List, Optional


def find_in_lock(lock: Dict[str, Any], model_name: str) -> Optional[Dict[str, Any]]:
    """在 lock 中查找模型
    
    Args:
        lock: Lock 数据字典
        model_name: 模型名称
        
    Returns:
        模型记录字典，未找到返回 None
    """
    models: List[Dict[str, Any]] = lock.get("models", [])
    for m in models:
        if m.get("model") == model_name:
            return m
    return None


def update_lock(lock: Dict[str, Any], entry: Dict[str, Any]) -> None:
    """更新或追加 lock 记录
    
    Args:
        lock: Lock 数据字典 (会被修改)
        entry: 新的模型记录
    """
    models: List[Dict[str, Any]] = lock.setdefault("models", [])
    model_name = entry.get("model")
    
    # 查找并更新已存在的记录
    for i, m in enumerate(models):
        if m.get("model") == model_name:
            models[i] = entry
            return
    
    # 不存在则追加
    models.append(entry)


def remove_from_lock(lock: Dict[str, Any], model_name: str) -> bool:
    """从 lock 中移除模型记录
    
    Args:
        lock: Lock 数据字典 (会被修改)
        model_name: 模型名称
        
    Returns:
        True 删除成功, False 未找到
    """
    models: List[Dict[str, Any]] = lock.get("models", [])
    for i, m in enumerate(models):
        if m.get("model") == model_name:
            models.pop(i)
            return True
    return False

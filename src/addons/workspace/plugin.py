"""Compatibility wrapper for workspace merge callers."""
from src.core.interface import BaseAddon
from src.lib.migration.merge import merge_directory


class WorkspaceAddon(BaseAddon):
    module_dir = "workspace"
    _merge_directory = staticmethod(merge_directory)

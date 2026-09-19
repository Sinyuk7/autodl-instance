"""Compatibility import; all layout policy lives in the migration module."""
from src.lib.migration import MigrationManager as DataLayout

__all__ = ["DataLayout"]

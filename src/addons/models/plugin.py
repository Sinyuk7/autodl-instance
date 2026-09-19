"""Model utilities live in tasks; installation never migrates user data."""
from src.core.interface import BaseAddon


class ModelAddon(BaseAddon):
    module_dir = "models"

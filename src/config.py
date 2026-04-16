"""Configuration loader for blog automation system."""

import os
from pathlib import Path

import yaml

_config = None
_project_root = Path(__file__).parent.parent


def get_project_root() -> Path:
    return _project_root


def load_config(config_path: str | None = None) -> dict:
    global _config
    if _config is not None and config_path is None:
        return _config

    if config_path is None:
        config_path = _project_root / "config.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f)

    return _config


def get_config() -> dict:
    if _config is None:
        return load_config()
    return _config

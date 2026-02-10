#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    def __init__(self, config_path: Optional[str] = None) -> None:
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = Path(__file__).parent / "user_config.json"

        self._config: Dict[str, Any] = {}
        self._load()

    def _default_config(self) -> Dict[str, Any]:
        return {
            "root_dir": "W:/S1UnrealSharedDoc",
            "test_root_dir": "",
            "max_read_bytes": 256 * 1024,
            "max_read_lines": 4000,
            "upload_max_bytes": 10 * 1024 * 1024,
            "mask_rules": {
                "enabled": False,
                "keyword_blacklist": [],
                "regex_blacklist": [],
            },
            "standards": {
                "default_paths": ["规范", "Standards", "Guidelines"],
                "keywords": ["规范", "Standard", "Guideline"],
            },
        }

    def _load(self) -> None:
        cfg = self._default_config()
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    cfg = self._deep_merge(cfg, data)
            except Exception:
                # 读配置失败时，仍然提供默认值，避免阻塞 Skill
                pass
        self._config = cfg

    def _save(self) -> None:
        self.config_path.write_text(json.dumps(self._config, ensure_ascii=False, indent=2), encoding="utf-8")

    def _deep_merge(self, base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(base)
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict):
                out[k] = self._deep_merge(out[k], v)
            else:
                out[k] = v
        return out

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._config:
            return self._config[key]
        return default

    def set(self, key: str, value: Any) -> None:
        self._config[key] = value
        self._save()

    def get_all(self) -> Dict[str, Any]:
        return dict(self._config)

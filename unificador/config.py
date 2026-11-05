"""
Gestor de configuración y registro de proyectos para Unificador.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from unificador.models import Project, AgentType


CONFIG_DIR = Path.home() / ".unificador"
CONFIG_FILE = CONFIG_DIR / "config.json"


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_FILE
        self.data: Dict[str, Any] = {
            "projects": [],
            "api_keys": {
                "deepseek": os.getenv("DEEPSEEK_API_KEY", ""),
                "openai": os.getenv("OPENAI_API_KEY", "")
            },
            "cli_paths": {
                "claude": "claude",
                "antigravity": "agy",
                "cursor": "cursor"
            },
            "settings": {
                "auto_commit_on_finish": False,
                "port": 8766,
                "host": "127.0.0.1"
            }
        }
        self.load()

    def load(self) -> None:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
            except Exception as e:
                print(f"[ConfigManager] Error al cargar configuración: {e}")
        else:
            self.save()

    def save(self) -> None:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ConfigManager] Error al guardar configuración: {e}")

    def get_projects(self) -> List[Project]:
        projects = []
        for p in self.data.get("projects", []):
            try:
                projects.append(Project(
                    id=p["id"],
                    name=p["name"],
                    path=p["path"],
                    color_theme=p.get("color_theme", "#3b82f6"),
                    active_phase_id=p.get("active_phase_id"),
                    default_agent=AgentType(p.get("default_agent", AgentType.CLAUDE_CODE.value)),
                    git_repo=p.get("git_repo"),
                    git_branch=p.get("git_branch", "main"),
                    created_at=p.get("created_at", 0.0)
                ))
            except Exception as e:
                print(f"[ConfigManager] Error parseando proyecto {p}: {e}")
        return projects

    def get_project(self, project_id: str) -> Optional[Project]:
        for p in self.get_projects():
            if p.id == project_id:
                return p
        return None

    def add_project(self, project: Project) -> None:
        projects = [p for p in self.data.get("projects", []) if p["id"] != project.id]
        projects.append(project.to_dict())
        self.data["projects"] = projects
        self.save()

    def remove_project(self, project_id: str) -> bool:
        initial_len = len(self.data.get("projects", []))
        self.data["projects"] = [p for p in self.data.get("projects", []) if p["id"] != project_id]
        if len(self.data["projects"]) < initial_len:
            self.save()
            return True
        return False

    def get_api_key(self, service: str) -> str:
        return self.data.get("api_keys", {}).get(service.lower(), "")

    def set_api_key(self, service: str, key: str) -> None:
        if "api_keys" not in self.data:
            self.data["api_keys"] = {}
        self.data["api_keys"][service.lower()] = key
        self.save()


# Instancia singleton para uso general
config = ConfigManager()

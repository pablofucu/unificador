"""
Gestor de configuración y registro de proyectos para Unificador.

- ``config.json``: proyectos, agentes y ajustes (sin secretos).
- ``credentials.json``: claves API, aparte y con permisos restringidos.
  Las variables de entorno tienen prioridad y nunca se escriben a disco.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import asdict
from unificador.models import Project, AgentType, AgentConfig, AppSettings


CONFIG_DIR = Path.home() / ".unificador"
CONFIG_FILE = CONFIG_DIR / "config.json"

ENV_VARS = {"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY"}

DEFAULT_AGENTS = {
    AgentType.CLAUDE_CODE: AgentConfig(AgentType.CLAUDE_CODE, command="claude"),
    AgentType.ANTIGRAVITY: AgentConfig(AgentType.ANTIGRAVITY, command="agy"),
    AgentType.CODEX: AgentConfig(AgentType.CODEX, command="cursor"),
    AgentType.DEEPSEEK: AgentConfig(AgentType.DEEPSEEK, model="deepseek-chat"),
}


def _write_json_atomic(path: Path, data: Any, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if private:
        try:
            os.chmod(tmp, 0o600)  # En Windows solo afecta al bit de solo lectura
        except OSError:
            pass
    os.replace(tmp, path)


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None,
                 credentials_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_FILE
        self.credentials_path = credentials_path or (
            self.config_path.parent / "credentials.json")
        self.data: Dict[str, Any] = {
            "projects": [],
            "agents": {a.value: c.to_dict() for a, c in DEFAULT_AGENTS.items()},
            "settings": asdict(AppSettings()),
        }
        self._credentials: Dict[str, str] = {}
        self.load()

    # ---------- Persistencia ----------
    def load(self) -> None:
        migrate = False
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.data["projects"] = loaded.get("projects", [])
                self.data["settings"].update(loaded.get("settings", {}))
                for name, cfg in loaded.get("agents", {}).items():
                    self.data["agents"].setdefault(name, {}).update(cfg)
                # Migración del formato antiguo (cli_paths / api_keys en config.json)
                legacy_cli = loaded.get("cli_paths", {})
                if legacy_cli and "agents" not in loaded:
                    for name, key in (("claude_code", "claude"),
                                      ("antigravity", "antigravity"),
                                      ("codex", "cursor")):
                        if key in legacy_cli:
                            self.data["agents"][name]["command"] = legacy_cli[key]
                legacy_keys = loaded.get("api_keys", {})
                if legacy_keys or legacy_cli:
                    migrate = True
                self._credentials = {k: v for k, v in legacy_keys.items() if v}
            except Exception as e:
                print(f"[ConfigManager] Error al cargar configuración: {e}")
        if self.credentials_path.exists():
            try:
                with open(self.credentials_path, "r", encoding="utf-8") as f:
                    self._credentials.update(json.load(f))
            except Exception as e:
                print(f"[ConfigManager] Error al cargar credenciales: {e}")
        if migrate or not self.config_path.exists():
            self.save()

    def save(self) -> None:
        try:
            _write_json_atomic(self.config_path, self.data)
            _write_json_atomic(self.credentials_path, self._credentials, private=True)
        except Exception as e:
            print(f"[ConfigManager] Error al guardar configuración: {e}")

    # ---------- Proyectos ----------
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

    # ---------- Agentes y ajustes ----------
    def get_agent_config(self, agent: AgentType) -> AgentConfig:
        raw = self.data["agents"].get(agent.value, {})
        try:
            return AgentConfig.from_dict({**DEFAULT_AGENTS[agent].to_dict(), **raw})
        except Exception:
            return DEFAULT_AGENTS[agent]

    def set_agent_config(self, cfg: AgentConfig) -> None:
        self.data["agents"][cfg.agent_type.value] = cfg.to_dict()
        self.save()

    def get_settings(self) -> AppSettings:
        defaults = asdict(AppSettings())
        raw = {k: v for k, v in self.data["settings"].items() if k in defaults}
        try:
            return AppSettings(**{**defaults, **raw})
        except Exception:
            return AppSettings()

    # ---------- Credenciales ----------
    def get_api_key(self, service: str) -> str:
        service = service.lower()
        env = os.getenv(ENV_VARS.get(service, f"{service.upper()}_API_KEY"), "")
        return env or self._credentials.get(service, "")

    def set_api_key(self, service: str, key: str) -> None:
        service = service.lower()
        if key:
            self._credentials[service] = key
        else:
            self._credentials.pop(service, None)
        self.save()

    def has_api_key(self, service: str) -> bool:
        return bool(self.get_api_key(service))


# Instancia singleton para uso general
config = ConfigManager()

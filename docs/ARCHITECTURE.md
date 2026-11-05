# Arquitectura del Sistema - Unificador

## 1. Propósito
Unificador es un orquestador local para desarrollo asistido por múltiples agentes de IA (Claude Code, Google Antigravity, OpenAI Codex / Cursor, y DeepSeek API). Centraliza el seguimiento de tareas en fases visuales basadas en Kanvas y ofrece una interfaz de chat con inyección contextual automática de prompts.

## 2. Componentes Principales

```
unificador/
├── __init__.py
├── config.py              # Gestión de proyectos, llaves de API y configuración
├── models.py              # Modelos de datos (Proyectos, Fases, Tareas, Agentes, Mensajes)
├── kanvas_bridge.py       # Lectura y manipulación programática de kanvas.json
├── context_injector.py    # Motor de ensamblado de prompts con contexto de proyecto y fase
├── git_service.py         # Automatización de Git (status, commit estructurado, push)
├── server.py              # Servidor HTTP API REST y SSE para el frontend
└── adapters/
    ├── __init__.py
    ├── base.py            # Contrato base de adaptador de IA (BaseAgentAdapter)
    ├── claude_code.py     # Integración CLI / terminal para Claude Code
    ├── antigravity.py     # Integración con Antigravity (agy CLI / protocolo)
    ├── codex.py           # Integración para Codex / Cursor
    └── deepseek.py        # Integración directa por API REST con streaming
```

## 3. Modelo de Inyección de Contexto
El motor intercepta el mensaje del usuario y construye un payload enriquecido:
- **Directorio de trabajo:** Ruta absoluta del proyecto en disco.
- **Fase y Tarea:** Nombre de la fase, ID de la tarea y descripción de los requisitos.
- **Protocolo de retroalimentación:** Instrucciones para que el agente reporte sus avances a Kanvas mediante notas (`kanvas note`) o cierre (`kanvas finish`).
- **Prompt del usuario:** La instrucción textual enviada desde el chat.

## 4. Multi-Proyecto y Fases
- Los proyectos se registran en `config.json` con metadatos: `id`, `name`, `path`, `color_theme`, `default_agent`.
- Las fases se mapean a partir de los grupos definidos en `kanvas.json` (ejemplo: `Fase 1: Configuración`, `Fase 2: Motor`, etc.) o de la profundidad topológica del grafo de dependencias.

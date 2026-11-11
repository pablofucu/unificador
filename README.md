# Unificador

El plan de tu proyecto y el chat con tus agentes de IA, en una web local muy sencilla.

- **El plan se ve de un vistazo**: ramas (áreas del proyecto) → fases con nombre → pasos pequeños.
- **Chat integrado** con Claude Code y Antigravity, eligiendo modelo, esfuerzo y modo.
- **Son las conversaciones de verdad**: lo que escribes en la web aparece en la terminal o en la
  aplicación del agente, y al revés. Unificador no guarda copias; lee y continúa las sesiones nativas.
- **Puedes corregir**: pide un cambio en cualquier paso y la IA lo retoma, o márcalo hecho a mano.
- **Sin dependencias**: solo Python 3.9 o superior. Nada de Node, ni bases de datos, ni cuentas.

## Ponerlo en marcha en un proyecto (dos pasos)

1. Instala Unificador una vez en tu ordenador:

   ```bash
   pip install git+https://github.com/pablofucu/unificador
   ```

   (o, si ya has clonado el repositorio, `pip install -e .` desde su carpeta).

2. Ábrelo en la carpeta de tu proyecto:

   ```bash
   unificador
   ```

Se abre el navegador con el plan a la izquierda y el chat a la derecha. La primera vez, Unificador deja
en el proyecto lo que la IA necesita para trabajar con el plan (no toca nada más):

| Fichero | Para qué |
| --- | --- |
| `unificador.json` | El plan. Aparece con la primera rama y se guarda con el proyecto (va a git). |
| `.unificador/uni.py` | La herramienta con la que la IA lee y actualiza el plan. |
| `.unificador/.gitignore` | Deja fuera de git tus preferencias locales. |
| `AGENTS.md`, `CLAUDE.md` | Un bloque marcado con las reglas de trabajo; el resto del fichero no se toca. |
| `.claude/settings.json` | Un aviso al empezar cada sesión de Claude Code con el estado del plan. |

Puedes seguir usando Claude Code o Antigravity por tu cuenta, como siempre: verán el mismo plan y sus
conversaciones aparecerán en la web.

## Órdenes

```text
unificador [RUTA] [--port N] [--no-open]    abre la web del proyecto (por defecto, la carpeta actual)
unificador install [RUTA]                   solo prepara el proyecto, sin abrir la web
unificador import-kanvas [RUTA] [--force]   convierte un tablero Kanvas (kanvas.json) en plan
```

La IA (y tú, si quieres) maneja el plan con `python .unificador/uni.py`:

```text
status · show ID · plan · add · start ID · note ID · done ID -m "qué cambió" · reopen ID · archive RAMA · drop RAMA
```

## Cómo se trabaja

1. Le pides algo a la IA en el chat (o en su terminal).
2. La IA lo convierte en una rama con fases y pasos, y los va haciendo: empieza, apunta, termina.
3. Tú lo ves moverse en directo. Si algo no te convence, abre el paso y pulsa **Pedir un cambio**.

Los modos del chat: **Autónomo** (hace el trabajo sin preguntar), **Edita sin preguntar** y **Solo planifica**.

## Agentes

| Agente | Qué necesita | Estado |
| --- | --- | --- |
| Claude Code | la orden `claude` | funciona |
| Antigravity | la orden `agy` | funciona |
| Codex | — | propuesta de futuro |

Un agente que no esté instalado aparece desactivado; el resto sigue funcionando.

## Desarrollo

```bash
python -m unittest discover -s tests
```

Cómo está hecho por dentro: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

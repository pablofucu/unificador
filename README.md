# Unificador

El plan de tu proyecto, a la vista, en una web local muy sencilla. Las conversaciones las llevas en el cliente de cada agente.

- **El plan se ve de un vistazo**: ramas (áreas del proyecto) → fases con nombre → pasos pequeños.
- **Tres clientes por igual**: Claude Code, Antigravity y Codex leen y actualizan el mismo plan.
- **La web solo enseña el plan**: no envía mensajes ni lee conversaciones; hablas con tu agente donde siempre.
- **Puedes corregir**: pide un cambio en cualquier paso (queda apuntado y el agente lo ve en su próximo repaso), o márcalo hecho a mano.
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

Se abre el navegador con el plan. La primera vez, Unificador deja
en el proyecto lo que la IA necesita para trabajar con el plan (no toca nada más):

| Fichero | Para qué |
| --- | --- |
| `unificador.json` | El plan. Aparece con la primera rama y se guarda con el proyecto (va a git). |
| `.unificador/uni.py` | La herramienta con la que la IA lee y actualiza el plan. |
| `.unificador/.gitignore` | Deja fuera de git tus preferencias locales. |
| `AGENTS.md`, `CLAUDE.md` | Un bloque marcado con las reglas de trabajo; el resto del fichero no se toca. |
| `.claude/settings.json` | Un aviso al empezar cada sesión de Claude Code con el estado del plan. |

Abre tu agente (Claude Code, Antigravity o Codex) en esa carpeta y trabajad como siempre: todos ven el mismo plan.

## Órdenes

```text
unificador [RUTA] [--port N] [--no-open]        abre la web del proyecto (por defecto, la carpeta actual)
unificador install [RUTA]                       solo prepara el proyecto, sin abrir la web
unificador doctor [RUTA]                        comprueba clientes (claude, agy, codex), reglas y Funnel
unificador import-kanvas [RUTA] [--force]       convierte un tablero Kanvas (kanvas.json) en plan
unificador funnel enable [RUTA] [--port 443]    activa URL pública con Tailscale Funnel, clave y autoarranque
unificador funnel status                        muestra URL pública, servidor activo y último proyecto
unificador funnel reset-key [--generate]        cambia la clave y cierra todas las sesiones abiertas
unificador funnel off                           desactiva el acceso público por Funnel
```

La IA (y tú, si quieres) maneja el plan con `python .unificador/uni.py`:

```text
status · show ID · branch · plan · add · start ID · note ID · done ID -m "qué cambió" · reopen ID · archive RAMA · drop RAMA
```

Una rama entera se apunta con una sola orden, igual en PowerShell, cmd y bash:

```text
python .unificador/uni.py branch "Carrito" --icon 🛒 --goal "Comprar desde la web" --phase "Cimientos" "Modelo" "Guardar" --phase "Pagos" "Pasarela" "Recibo"
```

## Cómo se trabaja

1. Le pides algo a tu agente, en su terminal o aplicación.
2. El agente lo convierte en una rama con fases y pasos, y los va haciendo: empieza, apunta, termina.
3. Tú lo ves moverse en directo en la web. Si algo no te convence, abre el paso y pulsa **Pedir un cambio**.

## Acceso remoto (Tailscale Funnel)

Si tienes Tailscale instalado en tu ordenador y quieres ver o aprobar tus planes desde el móvil o desde cualquier sitio:

```bash
unificador funnel enable
```

- **Puerta cerrada aunque se filtre la URL**: sin la clave correcta nadie ve nombres de proyectos, rutas, pasos ni propuestas; solo aparece una pantalla de acceso y todo lo demás responde `401`.
- **Puerto e inicio automático**: usa el puerto público `443` (o `8443` / `10000` si está ocupado, configurable con `--port`) apuntando al servidor local (`127.0.0.1:8766`). Cada vez que tú o un agente trabajáis en un proyecto con `uni.py`, se levanta el servidor en segundo plano si estaba parado y se marca ese proyecto como el activo.
- **Copia de caché sin conexión**: una vez dentro desde fuera, Unificador registra un Service Worker (`sw.js`) y se puede instalar en el móvil. Si apagas o suspendes el ordenador, sigues viendo el último tablero cargado en modo **solo lectura** (con aviso arriba). Al cerrar sesión o caducar la clave, la caché se borra automáticamente.
- **Revocar sesiones**: si sospechas que alguien tiene tu clave o tu móvil, ejecuta `unificador funnel reset-key` para cambiar la clave e invalidar todas las cookies al instante.

## Clientes

| Cliente | Orden | Lee las reglas de |
| --- | --- | --- |
| Claude Code | `claude` | `CLAUDE.md` (importa `AGENTS.md`) y el aviso de inicio de `.claude/settings.json` |
| Antigravity | `agy` | `AGENTS.md` |
| Codex | `codex` | `AGENTS.md` |

`unificador doctor` dice cuáles encuentra (en el PATH y en sus carpetas habituales) y si el proyecto tiene
sus reglas. Que falte un cliente no es un error: solo se informa.

## Desarrollo

```bash
python -m unittest discover -s tests
```

Cómo está hecho por dentro: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

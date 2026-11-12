# Plan: interfaz de andenes (rama IN2)

Maqueta elegida: `design/mockups/interfaz-andenes/andenes.html` (B. Andenes v2). Decidido con la persona el 12-nov-2026:

- **Categorías:** cinco fijas — `codigo`, `interfaz`, `pruebas`, `investigar`, `decidir`. Obligatorias en cada paso nuevo.
- **Lienzo:** colocación automática; la persona solo hace zoom y se desplaza. No se arrastran andenes ni pasos.
- **Decisiones:** ficha estándar con contexto en Markdown ligero, opciones con una línea de qué implican y la recomendada.
- **Un proyecto por defecto** con selector arriba (la portada de todos los proyectos sigue existiendo, pero no es la entrada).
- Sin emojis en la interfaz: iconos SVG.

## Fase 2 · Categorías y reglas del plan (solo backend: `plan.py`, `rules.py`, `app.py`, `tests/`)

### Formato nuevo (campos opcionales: los planes viejos siguen cargando)

```text
paso:    ... cat: "codigo"|"interfaz"|"pruebas"|"investigar"|"decidir",  together: true  (a la vez que el anterior)
fase:    ... after: [{"branch": "PM", "phase": "Biblioteca"}]          (no empieza hasta que esa acabe)
ask:     ... text: contexto en Markdown ligero (≤ 800 caracteres), recommend: 1..n | 0 (sin preferencia) | null (viejas)
opción:  ... label, desc (una línea, ≤ 160), file (propuestas)
```

Markdown ligero = párrafos, `**negrita**`, `*cursiva*`, `` `código` ``, listas con `- `. Nada más (la web lo pinta con nodos, nunca con innerHTML).

### Órdenes

- Pasos con categoría como prefijo, en `branch` y en `add`: `"interfaz: Elegir colores"`. Alias sin tilde y en inglés
  (`código|codigo|code`, `interfaz|ui|diseño`, `pruebas|prueba|test|probar`, `investigar|investigación|research`,
  `decidir|decisión|decision`). Un `+` delante = a la vez que el anterior: `"+pruebas: Probar en tablet"`.
  Sin categoría válida → se rechaza toda la orden con un mensaje que enseña las cinco y un ejemplo.
- `uni.py cat ID categoria` pone o cambia la categoría de un paso (para planes viejos).
- `uni.py after RAMA "Fase" OTRA "Fase otra"`: la primera espera a la segunda. Rechaza ciclos y fases inexistentes.
  `start` de un paso cuya fase espera a otra sin terminar → rechazo con `--force` para saltárselo a sabiendas.
- `ask`: `--option "Título | qué implica"` (la descripción es obligatoria si hay opciones) y `--recommend N`
  (obligatorio si hay opciones; `0` = sin preferencia). `-d` es el contexto.
- `propose`: `--option "Nombre | qué cambia" ruta.html` y `--recommend N`, igual.

### HTML de propuestas listo para incrustar (al copiarlo a `.unificador/propuestas/`)

- Si es un fragmento (sin `<html>` ni `<body>`), se envuelve en un esqueleto con `charset`, `viewport`, fuente del sistema y márgenes.
- Si es un documento sin `<meta name="viewport">`, se le añade.
- Recursos de fuera (`http(s)://` o `//` en `src`, `href` de `<link>`, `url(...)`, `@import`) → rechazo con fichero y línea.
  Los enlaces `<a href>` no cuentan. `data:` sí vale.

### Revisión de cumplimiento

- `plan.audit(plan) -> [{"level": "error"|"aviso", "ref": "IN2-3"|"P-4"|"IN2/Fase", "text": "..."}]`:
  paso sin categoría; paso hecho cuyo resultado no dice cómo se comprobó (menos de 25 caracteres o sin ninguna de
  comprob|prueb|test|captur|verific|pasa|ejecut|revis); pregunta abierta con opciones sin `desc` o sin `recommend`;
  propuesta con fichero que falta; fase con nombre genérico; dependencia que apunta a una fase que ya no existe.
- `uni.py check`: imprime la lista agrupada; sale con 1 si hay algún «error».
- `GET /api/plan` añade `audit` (la misma lista) para que la web lo enseñe.
- `status` acaba con una línea «Avisos: N (python .unificador/uni.py check)» si hay alguno.

### Reglas para los agentes

El bloque de `rules.py` (lo que va a `AGENTS.md`/`CLAUDE.md`) se actualiza con la sintaxis nueva, corto: categorías,
`+`, `after`, ficha de `ask`/`propose`, y «antes de cerrar una fase, `check` sin errores». Lo mismo en `EXAMPLE` y `BRANCH_HINT`.

## Fase 3 · Montar el diseño elegido (solo `web/` y, si hace falta, `app.py`)

- Lienzo de andenes como la maqueta: una línea por rama (código, nombre, progreso), andenes por fase con sus pasos,
  icono SVG por categoría, «A la vez» agrupado, dependencias como enlace punteado, parada al cerrar fase con
  Aprobar / Pedir cambios. Zoom (botones y rueda con Ctrl) y desplazamiento; colocación automática.
- Cabecera: selector de proyecto, chips de categoría que filtran, botón «Decisiones N» que abre la bandeja.
- Decisiones dentro del andén: ficha (contexto en Markdown ligero, opciones con su línea, «Recomendada»),
  propuestas en miniatura a escala real (1280 de ancho lógico) y visor a pantalla completa (lo de `decide.js` se reutiliza).
- Avisos de cumplimiento: chip discreto en el paso o la decisión afectada, con el texto en el detalle.
- Móvil y tablet: por debajo de 760 px las líneas se apilan y los andenes van uno debajo de otro; objetivos de 44 px.
- Comprobación: capturas en Edge sin ventana a 1440, 1024 y 390 px, y la batería de pruebas.

## Cómo se trabaja

- Implementan subagentes Sonnet (`implementador`) con un brief cerrado; no hacen commit.
- Claude (Opus) revisa cada diff contra este plan, pasa `python -m pytest -q`, prueba las órdenes a mano y hace commit y push.
- Al cerrar cada fase se para y se pregunta a la persona.

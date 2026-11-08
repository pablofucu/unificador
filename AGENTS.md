# Agent instructions

Plan and track work on the Kanvas board; follow .agents/skills/kanvas/SKILL.md.

<!-- unificador:inicio (lo mantiene Unificador; los cambios aquí se pierden) -->
## Trabajo por ramas, fases y pasos (Unificador)

La persona sigue este proyecto en Unificador, que muestra el tablero Kanvas como ramas → fases → pasos,
y también te habla desde la terminal. Trabaja igual en los dos sitios:

1. Al empezar, mira el tablero (`python .agents/skills/kanvas/kanvas.py status`) y cuéntale a la persona qué le toca revisar,
   qué está en curso y qué sigue.
2. Todo trabajo nuevo que no esté ya en el tablero se planifica antes de programar: propón los pasos con
   **una sola** orden `batch` (llegan como propuestas), resume el plan fase a fase y **para** hasta que la
   persona lo apruebe en Unificador o en el tablero.
3. Haz cada paso con `start` → `note` → `finish` (firma con `--as`); no programes trabajo que no tenga paso.

### CÓMO SE ORGANIZA EL TRABAJO: RAMAS → FASES → PASOS
- Cada **grupo** de Kanvas es una **rama**: un área del proyecto que puede avanzar por su cuenta (p. ej. «Interfaz», «Datos», «Despliegue»). Nombra los grupos por el área, no por el orden: nada de «Fase 1: …».
- Dentro de cada rama, las **fases** salen de las dependencias: un paso que depende (`deps`) de otro de la misma rama va en la fase siguiente. Sin dependencias, todo cae en la fase 1.
- Cada **paso** es una tarea pequeña y comprobable (una sesión de trabajo), con una `desc` que diga qué consigue y cuándo está terminada.
- Trabaja fase a fase: no empieces un paso cuyas dependencias no estén hechas.

- Encadena los pasos con `deps` para que cada rama tenga entre 2 y 5 fases; evita ramas de un solo paso gigante.
- `deps` acepta los títulos de pasos del mismo batch. Si la orden falla, lee el error y corrige el JSON.
- Si la petición es una pregunta o un cambio diminuto, contesta sin planificar.
<!-- unificador:fin -->

# Agent instructions

Este proyecto es Unificador y se sigue con su propio plan (abajo). Cómo está hecho: docs/ARCHITECTURE.md.

<!-- unificador:inicio (lo mantiene Unificador; los cambios aquí se pierden) -->
## El plan del proyecto (Unificador)

La persona sigue este proyecto en Unificador, que enseña el plan como **ramas → fases → pasos**.
El plan vive en `unificador.json` y se toca solo con `python .unificador/uni.py` (nunca edites el JSON a mano).
Vale igual si te hablan desde la web, la terminal o la app.

- **Al empezar**, mira cómo va: `python .unificador/uni.py status`. Si un paso dice «PIDE CAMBIOS», atiéndelo lo primero.
- **Trabajo nuevo** (algo más que una pregunta o un retoque): apúntalo ANTES de empezar, como una rama,
  con esta única orden (vale en PowerShell, cmd y bash; cada cosa entre comillas dobles):

  ```
  python .unificador/uni.py branch "Carrito de compra" --icon 🛒 --goal "Poder comprar desde la web" --phase "Cimientos" "Modelo del carrito" "Guardar y recuperar" --phase "Pagos" "Pasarela de pago" "Recibo por correo"
  ```

  - Una **rama** es una función o un conjunto de cosas que hacer. Detrás de cada `--phase` va el nombre
    de la fase y después sus pasos.
  - Entre 2 y 4 **fases** por rama, en orden, con un nombre que se reconozca («Cimientos», «Pagos», «Pulido»).
    «Fase 1» o «Etapa 2» se rechazan. **Pasos** pequeños y comprobables, con título corto en lenguaje llano.
  - No pidas permiso ni confirmación para apuntar el plan: hazlo y sigue. La persona te corregirá si algo no encaja.
  - Para añadir un paso suelto a una rama que ya existe: `python .unificador/uni.py add RAMA "Fase" "Título"`.
- **En cada paso**: `python .unificador/uni.py start ID` → trabaja → `python .unificador/uni.py done ID -m "qué ha cambiado y cómo lo has comprobado"`.
  Cada orden te dice cuál es la siguiente. Termina las fases en orden; si descubres algo que la persona
  deba saber, `python .unificador/uni.py note ID "…"`.
- Firma con `--as <tu nombre>` (por ejemplo `--as claude`) salvo que `UNI_AGENT` ya esté puesto.
- Preguntas y cambios diminutos: contesta sin tocar el plan.
<!-- unificador:fin -->

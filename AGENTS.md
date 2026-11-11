# Agent instructions

Este proyecto es Unificador y se sigue con su propio plan (abajo). Cómo está hecho: docs/ARCHITECTURE.md.

<!-- unificador:inicio (lo mantiene Unificador; los cambios aquí se pierden) -->
## El plan del proyecto (Unificador)

La persona sigue este proyecto en Unificador, que enseña el plan como **ramas → fases → pasos**.
El plan vive en `unificador.json` y se toca solo con `python .unificador/uni.py` (nunca edites el JSON a mano).
Vale igual si te hablan desde la web, la terminal o la app.

- **Al empezar**, mira cómo va: `python .unificador/uni.py status`. Si un paso dice «PIDE CAMBIOS», atiéndelo lo primero.
- **Trabajo nuevo** (algo más que una pregunta o un retoque): apúntalo como una rama y ponte con él.
  No hace falta que nadie lo apruebe; la persona te corregirá si algo no le encaja.

  ```
  python .unificador/uni.py plan <<'EOF'
  {"branches": [{
    "name": "Carrito de compra", "icon": "🛒", "goal": "Poder comprar desde la web",
    "phases": [
      {"name": "Cimientos", "steps": [{"title": "Modelo del carrito", "desc": "Hecho cuando se guarda y se recupera"}]},
      {"name": "Pagos", "steps": [{"title": "Pasarela de pago"}, {"title": "Recibo por correo"}]}
    ]}]}
  EOF
  ```

  - Una **rama** es un cambio o un área que avanza por su cuenta. Ponle un emoji en `icon`.
  - Entre 2 y 4 **fases** por rama, en orden, con un nombre que se reconozca de un vistazo
    («Cimientos», «Pagos», «Pulido»). «Fase 1» o «Etapa 2» se rechazan.
  - **Pasos** pequeños y comprobables, con título corto en lenguaje llano.
  - Para añadir un paso suelto a una rama que ya existe: `python .unificador/uni.py add RAMA "Fase" "Título" -d "…"`.
- **En cada paso**: `python .unificador/uni.py start ID` → trabaja → `python .unificador/uni.py done ID -m "qué ha cambiado y cómo lo has comprobado"`.
  Si descubres algo que la persona deba saber, `python .unificador/uni.py note ID "…"`. Termina las fases en orden.
- Firma con `--as <tu nombre>` (por ejemplo `--as claude`) salvo que `UNI_AGENT` ya esté puesto.
- Preguntas y cambios diminutos: contesta sin tocar el plan.
<!-- unificador:fin -->

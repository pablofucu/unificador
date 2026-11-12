"""Monta cada mockup autocontenido: base.css + base.js + el fragmento dN-*.html -> ../N-nombre.html"""
from pathlib import Path

src = Path(__file__).parent
css, js = (src / "base.css").read_text("utf-8"), (src / "base.js").read_text("utf-8")
SHELL = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Unificador · {name}</title>
<style>{css}</style></head><body>
<header class="top"><b class="logo">🧩 Unificador</b><nav id="nav"></nav><div id="legend"></div>
<button class="help" title="¿Qué es cada cosa?">?</button><span class="tag"></span></header>
<main id="root"></main><div id="sheet"></div>
<div id="gloss"><span class="eyebrow">Cómo se lee</span>
<b>🌿 Rama</b><span>Una función o un conjunto de cosas que hacer. Varias ramas pueden avanzar a la vez.</span>
<b>🧱 Fase</b><span>Un tramo de la rama con nombre propio («Pagos», «Pulido»). Al cerrarla, el agente para y te pregunta.</span>
<b>✅ Paso</b><span>Una cosa pequeña y comprobable. Lleva siempre una categoría: código, interfaz, pruebas, investigar o decidir.</span>
<b>⇉ A la vez</b><span>Pasos de una misma fase que se hacen al mismo tiempo.</span>
<b>🔒 Espera a…</b><span>Una fase que no empieza hasta que acabe otra.</span></div>
<script>{js}</script>
{frag}
</body></html>"""
for f in sorted(src.glob("d*.html")):
    name = f.stem[1:]
    out = src.parent / f"{name}.html"
    out.write_text(SHELL.format(name=name, css=css, js=js, frag=f.read_text("utf-8")), "utf-8")
    print(out.name, out.stat().st_size // 1024, "KB")

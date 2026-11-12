"""Monta cada mockup autocontenido (base.css + metro.css + base.js + fragmento dX-*.html) y uno con pestañas que los junta."""
import base64
import json
from pathlib import Path

src = Path(__file__).parent
css = (src / "base.css").read_text("utf-8") + (src / "metro.css").read_text("utf-8")
js = (src / "base.js").read_text("utf-8")
SHELL = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Unificador · {name}</title>
<style>{css}</style></head><body>
<header class="top"><b class="logo">🧩 Unificador</b><nav id="nav"></nav><div id="legend"></div>
<button class="help" title="¿Qué es cada cosa?">?</button><span class="tag"></span></header>
<main id="root"></main><div id="sheet"></div>
<div id="gloss"><span class="eyebrow">Cómo se lee</span>
<b>🌈 Proyecto</b><span>Cada proyecto tiene un color. Juntos van ordenados como un arcoíris.</span>
<b>🚇 Rama</b><span>Una línea. Cada rama es un tono del color de su proyecto.</span>
<b>🧱 Fase</b><span>Un tramo de la línea con nombre propio. Al cerrarla, el agente para y te pregunta.</span>
<b>✅ Paso</b><span>Una tarjeta. Lleva su etiqueta (código, interfaz, pruebas, investigar o decidir) y una marca cuando está hecho.</span>
<b>⇉ A la vez</b><span>La línea se abre en dos: pasos que se hacen al mismo tiempo.</span>
<b>🔒 Enlace punteado</b><span>Una fase que no empieza hasta que acabe otra de otra línea.</span></div>
<script>{js}</script>
{frag}
</body></html>"""
made = []
for f in sorted(src.glob("d*.html")):
    name = f.stem[1:]
    out = src.parent / f"{name}.html"
    out.write_text(SHELL.format(name=name, css=css, js=js, frag=f.read_text("utf-8")), "utf-8")
    made.append(out)
    print(out.name, out.stat().st_size // 1024, "KB")

docs = json.dumps([base64.b64encode(o.read_bytes()).decode() for o in made])
tabs = "".join('<button data-i="%d">%s</button>' % (i, o.stem.replace("-", " · ", 1).capitalize()) for i, o in enumerate(made))
ALL = """<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unificador · Metro con tarjetas</title>
<style>html,body{margin:0;height:100%;font-family:system-ui,"Segoe UI",sans-serif;background:#1f2338}
body{display:flex;flex-direction:column}
nav{display:flex;gap:6px;padding:8px 10px;overflow-x:auto;align-items:center;flex:none}
nav b{color:#fff;font-size:13px;margin-right:6px;white-space:nowrap;opacity:.8}
nav button{border:0;border-radius:99px;padding:9px 16px;font:inherit;font-size:14px;font-weight:700;background:#353a58;color:#dfe3f3;cursor:pointer;white-space:nowrap}
nav button.on{background:#fff;color:#1f2338}
iframe{flex:1;border:0;width:100%;background:#f6f7fb;border-radius:14px 14px 0 0}</style>
<nav><b>Metro con tarjetas</b>@TABS@</nav><iframe id="f" title="Propuesta"></iframe>
<script>const DOCS=@DOCS@;
const urls=DOCS.map(d=>URL.createObjectURL(new Blob([Uint8Array.from(atob(d),c=>c.charCodeAt(0))],{type:"text/html;charset=utf-8"})));
const f=document.getElementById("f"),bs=[...document.querySelectorAll("nav button")];
function show(i){let hsh="#/";try{hsh=f.contentWindow.location.hash||"#/"}catch(e){}f.src=urls[i]+hsh;bs.forEach((b,k)=>b.classList.toggle("on",k==i))}
bs.forEach(b=>b.onclick=()=>show(+b.dataset.i));show(0);</script></html>
"""
out = src.parent / "todas.html"
out.write_text(ALL.replace("@TABS@", tabs).replace("@DOCS@", docs), encoding="utf-8")
print(out.name, out.stat().st_size // 1024, "KB")

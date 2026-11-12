"""Junta todas las propuestas en un único HTML con pestañas: ../todas-las-propuestas.html"""
import base64
import json
import pathlib

AQUI = pathlib.Path(__file__).parent.parent
D = [("1-carriles", "1 · Carriles"), ("2-metro", "2 · Metro"), ("3-orbitas", "3 · Órbitas"),
     ("4-baraja", "4 · Baraja"), ("5-ahora", "5 · Línea del ahora")]
docs = json.dumps([base64.b64encode((AQUI / (f + ".html")).read_bytes()).decode() for f, _ in D])
tabs = "".join('<button data-i="%d">%s</button>' % (i, n) for i, (_, n) in enumerate(D))
HTML = """<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unificador · propuestas de interfaz</title>
<style>html,body{margin:0;height:100%;font-family:system-ui,"Segoe UI",sans-serif;background:#1f2338}
body{display:flex;flex-direction:column}
nav{display:flex;gap:6px;padding:8px 10px;overflow-x:auto;align-items:center;flex:none}
nav b{color:#fff;font-size:13px;margin-right:6px;white-space:nowrap;opacity:.8}
nav button{border:0;border-radius:99px;padding:9px 16px;font:inherit;font-size:14px;font-weight:700;background:#353a58;color:#dfe3f3;cursor:pointer;white-space:nowrap}
nav button.on{background:#fff;color:#1f2338}
iframe{flex:1;border:0;width:100%;background:#f6f7fb;border-radius:14px 14px 0 0}</style>
<nav><b>Propuestas</b>@TABS@</nav><iframe id="f" title="Propuesta"></iframe>
<script>const DOCS=@DOCS@;
const urls=DOCS.map(d=>URL.createObjectURL(new Blob([Uint8Array.from(atob(d),c=>c.charCodeAt(0))],{type:"text/html;charset=utf-8"})));
const f=document.getElementById("f"),bs=[...document.querySelectorAll("nav button")];
function show(i){let hsh="#/";try{hsh=f.contentWindow.location.hash||"#/"}catch(e){}f.src=urls[i]+hsh;bs.forEach((b,k)=>b.classList.toggle("on",k==i))}
bs.forEach(b=>b.onclick=()=>show(+b.dataset.i));show(0);</script></html>
"""
out = AQUI / "todas-las-propuestas.html"
out.write_text(HTML.replace("@TABS@", tabs).replace("@DOCS@", docs), encoding="utf-8")
print(out, out.stat().st_size)

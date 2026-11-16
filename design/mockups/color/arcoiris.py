"""Variantes arcoíris del estilo Pop a partir de una captura del tablero con todas las ramas (snap2.html)."""
import io, re, sys, pathlib
here = pathlib.Path(__file__).parent
web = here.parents[2] / "unificador" / "web"
snap = io.open(sys.argv[1], encoding="utf-8").read()
for n in ("app.css", "decide.css"):
    snap = snap.replace(f'<link rel="stylesheet" href="{n}">', "<style>" + io.open(web / n, encoding="utf-8").read() + "</style>")
snap = re.sub(r"<link[^>]*>", "", snap)
# Cada rama toma el color por su orden en pantalla (de arriba abajo: rojo, naranja, amarillo...).
k = iter(range(10**6))
snap = re.sub(r'(<section class="row[^"]*"[^>]*?) data-color="\d"', lambda m: f'{m.group(1)} data-color="{next(k) % 8}"', snap)

RAIN = [("#ef4444", "#fee2e2"), ("#f97316", "#ffedd5"), ("#facc15", "#fef9c3"), ("#22c55e", "#dcfce7"),
        ("#06b6d4", "#cffafe"), ("#3b82f6", "#dbeafe"), ("#8b5cf6", "#ede9fe"), ("#ec4899", "#fce7f3")]
PAL = "".join(f'[data-color="{i}"]{{--accent:{a};--tint:{t}}}' for i, (a, t) in enumerate(RAIN))
INK = "#1b1b1b"
STATIC = ".sizer{width:auto!important;height:auto!important;display:flex;min-width:100%}.m-box{position:relative!important;left:0!important;margin:0 auto}"
POP = f"""
body{{background-color:#fff4dc;background-image:radial-gradient(#efd29b 1.3px,transparent 1.3px);background-size:18px 18px}}
.canvas-wrap{{background:#fffdf6;border:3px solid {INK};box-shadow:6px 6px 0 {INK}}}
.pc,.pc.st-d,.pc.st-w{{border:3px solid {INK};border-radius:16px;box-shadow:6px 6px 0 {INK}}}
.pch,.pc.st-d .pch{{background:var(--c);color:{INK};border-bottom:3px solid {INK};border-radius:13px 13px 0 0}}
.pc.st-p .pch{{background:var(--tint);color:{INK}}}
.nb,.pc.st-d .nb,.pc.st-w .nb{{background:#fff;color:{INK};border:2.5px solid {INK}}}
.pc .ok-tag,.pc:not(.st-d) .ok-tag{{background:#fff;color:{INK}}}
.head{{border:3px solid {INK};box-shadow:6px 6px 0 {INK};color:{INK}}}
.hbar{{background:rgba(255,255,255,.5);border:1.5px solid {INK}}}.hbar i{{background:{INK}}}
.switch{{border:2px solid {INK};background:#fff}}.nonstop .act-msg{{color:{INK}}}
.code{{border:2px solid {INK};color:{INK}}}
.chip-cat{{background:var(--k);color:#fff;border:2.5px solid {INK};box-shadow:3px 3px 0 {INK}}}
.chip-cat[data-c=""]{{background:#fff;color:{INK}}}
.ci{{background:var(--k);color:#fff;border:2px solid {INK}}}
.bx{{border-color:{INK}}}.step.done .bx{{border-color:{INK};color:{INK}}}
.mix{{border:2px solid {INK};background:#fff;height:12px}}.mix i{{border-right:2px solid {INK};border-radius:0}}
.end{{border:3px solid {INK}}}.end.ok{{border-color:{INK};color:{INK}}}
.rail{{opacity:.55}}.rail.on{{opacity:1}}
.decb{{background:#ffd23f;color:{INK};border:3px solid {INK};box-shadow:4px 4px 0 {INK}}}.decb .n{{background:{INK};color:#fff}}
.pick select,.tb .total{{background:#fff;border:3px solid {INK};box-shadow:4px 4px 0 {INK}}}
.zoom{{border:3px solid {INK};box-shadow:4px 4px 0 {INK}}}
"""
# Las vías del SVG se tiñen con el color de la rama que tienen a su altura.
FIX_RAILS = """<script>addEventListener('load',()=>{const box=document.getElementById('branches');const rows=[...box.querySelectorAll('.row')];
for(const p of box.querySelectorAll('svg.layer [stroke]')){const m=/M\\s*[-\\d.]+[ ,]([-\\d.]+)/.exec(p.getAttribute('d')||'');if(!m)continue;const y=+m[1];
const r=rows.find(r=>y>=r.offsetTop-20&&y<=r.offsetTop+r.offsetHeight+20);if(r){const c=getComputedStyle(r.querySelector('.pc')||r).getPropertyValue('--c').trim();if(c)p.setAttribute('stroke',c)}}});</script>"""

DIAG = "".join(f'.row[data-color="{i}"] .phases>li:nth-child({j + 1}){{--c:{RAIN[(i + j + 1) % 8][0]};--tint:{RAIN[(i + j + 1) % 8][1]}}}'
               for i in range(8) for j in range(6))
CATS = {"interfaz": RAIN[0][0], "investigar": RAIN[1][0], "pruebas": RAIN[3][0], "codigo": RAIN[5][0], "decidir": RAIN[6][0]}
OLD = {"interfaz": "#e0559a", "investigar": "#e8930c", "pruebas": "#1fa971", "codigo": "#4f6bed", "decidir": "#8b5cf6"}
ORDER = ["", "interfaz", "investigar", "pruebas", "codigo", "decidir"]
TOPE = "".join(f'.chip-cat[data-c="{c}"],.ci[style*="{OLD[c]}"]{{--k:{CATS[c]}!important}}' for c in CATS)
TOPE += ".legend{display:flex}" + "".join(f'.chip-cat[data-c="{c}"]{{order:{i}}}' for i, c in enumerate(ORDER))
BOW = "linear-gradient(90deg," + ",".join(a for a, _ in RAIN[:7]) + ")"
TOPE += f"""
.canvas-wrap{{border-top:12px solid transparent;border-image:{BOW} 1;border-image-slice:1}}
.canvas-wrap{{border:3px solid {INK};border-top:0}}.canvas-wrap::before{{content:"";position:absolute;left:0;right:0;top:0;height:12px;background:{BOW};border-bottom:3px solid {INK};z-index:5}}
.mix i{{background:{BOW};background-size:300px 100%}}
.tb .bar i,#total-bar{{background:{BOW}!important}}
.decb{{background:{BOW};color:{INK}}}
.donebar button{{border:2.5px solid {INK};background:#fff;box-shadow:3px 3px 0 {INK}}}
"""
V = {"5-ramas": PAL, "6-diagonal": PAL + DIAG, "7-a-tope": PAL + TOPE}
for name, extra in V.items():
    out = snap.replace("</head>", f"<style>{STATIC}{POP}{extra}</style></head>").replace("</body>", FIX_RAILS + "</body>")
    io.open(here / f"{name}.html", "w", encoding="utf-8").write(out)
    print(name, len(out))

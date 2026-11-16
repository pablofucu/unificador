"""Genera las propuestas de color a partir de una captura del tablero real (snap.html) y app.css/decide.css."""
import io, re, sys, pathlib
here = pathlib.Path(__file__).parent
web = here.parents[2] / "unificador" / "web"
snap = io.open(sys.argv[1], encoding="utf-8").read()
css = {n: io.open(web / n, encoding="utf-8").read() for n in ("app.css", "decide.css")}
for n, c in css.items():
    snap = snap.replace(f'<link rel="stylesheet" href="{n}">', f"<style>{c}</style>")
snap = re.sub(r"<link[^>]*>", "", snap)
STATIC = """
.sizer{width:auto!important;height:auto!important;display:flex;min-width:100%}
.m-box{position:relative!important;left:0!important;margin:0 auto}
"""
T = {}
T["1-pastel"] = """
body{background:radial-gradient(1100px 600px at 8% 0%,#ffe1f0,transparent 60%),radial-gradient(900px 600px at 95% 5%,#dcefff,transparent 60%),radial-gradient(1000px 700px at 50% 110%,#e2fbe9,transparent 60%),#fbf7ff}
.canvas-wrap{background:rgba(255,255,255,.4);border-color:#fff;box-shadow:0 10px 40px rgba(120,90,200,.10)}
.pc{background:linear-gradient(180deg,var(--tint),#fff 75%);border-color:color-mix(in srgb,var(--c) 45%,#fff)}
.pch{background:color-mix(in srgb,var(--c) 24%,#fff)}
.pc.st-p .pch{background:color-mix(in srgb,var(--c) 12%,#fff)}
.nb{background:#fff;color:var(--c)}
.head{background:linear-gradient(135deg,var(--c),color-mix(in srgb,var(--c) 55%,#fff))}
.mix{background:color-mix(in srgb,var(--c) 16%,#fff)}
.rail{opacity:.35}
.pick select,.tb .total{background:#fff;border-color:#fff;box-shadow:0 4px 14px rgba(120,90,200,.10)}
.decb{background:linear-gradient(135deg,#8b5cf6,#ec4899)}
"""
T["2-caramelo"] = """
body{background:linear-gradient(135deg,#fff1d6 0%,#ffe0ec 50%,#e3e6ff 100%)}
.canvas-wrap{background:rgba(255,255,255,.45);border-color:rgba(255,255,255,.8)}
.pc{border:0;box-shadow:0 7px 0 color-mix(in srgb,var(--c) 40%,transparent),0 14px 30px rgba(0,0,0,.08)}
.pch,.pc.st-d .pch{background:var(--c);color:#fff}
.pc.st-p .pch{background:color-mix(in srgb,var(--c) 72%,#fff);color:#fff}
.nb{background:rgba(255,255,255,.28);color:#fff}
.pc.st-d .nb,.pc.st-w .nb{background:#fff;color:var(--c)}
.pc:not(.st-d) .ok-tag{background:rgba(255,255,255,.3);color:#fff}
.bx{border-color:color-mix(in srgb,var(--c) 70%,#fff)}
.chip-cat{background:var(--k);color:#fff}
.chip-cat[data-c=""]{background:#1f2338;color:#fff}
.ci{background:var(--k);color:#fff}
.rail{opacity:.45;stroke-width:16}
.mix{background:color-mix(in srgb,var(--c) 18%,#fff);height:10px}
.head{box-shadow:0 7px 0 color-mix(in srgb,var(--c) 65%,#000)}
.decb{background:#ff4f87}
"""
T["3-neon"] = """
:root{color-scheme:dark;--bg:#0d0f1f;--panel:#171a33;--card:#1b1f3b;--ink:#eef0ff;--muted:#9aa0c3;--line:#2a2f55;--soft:#252a4d}
body{background:radial-gradient(900px 500px at 12% 0%,#2c1a63,transparent 60%),radial-gradient(800px 520px at 88% 100%,#0e3d5c,transparent 60%),#0d0f1f;color:var(--ink)}
.canvas-wrap{background:rgba(255,255,255,.03);border-color:#2a2f55}
.pc{background:#171a33;border-color:color-mix(in srgb,var(--c) 65%,#171a33);box-shadow:0 0 26px color-mix(in srgb,var(--c) 38%,transparent)}
.pch{background:color-mix(in srgb,var(--c) 28%,#171a33)}
.pc.st-p .pch{background:#20244a}
.s-btn:hover{background:color-mix(in srgb,var(--c) 18%,#171a33)}
.step.open>.srow>.s-btn{background:color-mix(in srgb,var(--c) 25%,#171a33)}
.bx{border-color:color-mix(in srgb,var(--c) 75%,#171a33)}
.ci{background:color-mix(in srgb,var(--k) 25%,#171a33);color:color-mix(in srgb,var(--k) 65%,#fff)}
.chip-cat{background:color-mix(in srgb,var(--k) 22%,#171a33);color:color-mix(in srgb,var(--k) 60%,#fff)}
.chip-cat[data-c=""]{background:#252a4d;color:#fff}
.pc:not(.st-d) .ok-tag{background:#252a4d;color:#fff}
.head{box-shadow:0 0 32px color-mix(in srgb,var(--c) 60%,transparent)}
.end{background:#171a33}
.dep0{stroke:#171a33}
.rail{opacity:.35}
.mix{background:#252a4d}
.pick select,.tb .total{background:#171a33;color:var(--ink);border-color:#2a2f55}
.decb{background:linear-gradient(135deg,#7c5cff,#00c2ff)}
.zoom{background:#171a33}
"""
T["4-pop"] = """
body{background-color:#fff4dc;background-image:radial-gradient(#efd29b 1.3px,transparent 1.3px);background-size:18px 18px}
.canvas-wrap{background:#fffdf6;border:3px solid #1b1b1b;box-shadow:6px 6px 0 #1b1b1b}
.pc,.pc.st-d,.pc.st-w{border:3px solid #1b1b1b;border-radius:16px;box-shadow:6px 6px 0 #1b1b1b}
.pch,.pc.st-d .pch{background:var(--c);color:#fff;border-bottom:3px solid #1b1b1b;border-radius:13px 13px 0 0}
.pc.st-p .pch{background:var(--tint);color:#1b1b1b}
.nb,.pc.st-d .nb,.pc.st-w .nb{background:#fff;color:#1b1b1b;border:2.5px solid #1b1b1b}
.pc:not(.st-d) .ok-tag{background:#fff;color:#1b1b1b}
.head{border:3px solid #1b1b1b;box-shadow:6px 6px 0 #1b1b1b}
.code{border:2px solid #1b1b1b}
.chip-cat{background:var(--k);color:#fff;border:2.5px solid #1b1b1b;box-shadow:3px 3px 0 #1b1b1b}
.chip-cat[data-c=""]{background:#fff;color:#1b1b1b}
.ci{background:var(--k);color:#fff;border:2px solid #1b1b1b}
.bx{border-color:#1b1b1b}
.mix{border:2px solid #1b1b1b;background:#fff;height:12px}
.end{border:3px solid #1b1b1b}
.rail{opacity:.55}
.decb{background:#ffd23f;color:#1b1b1b;border:3px solid #1b1b1b;box-shadow:4px 4px 0 #1b1b1b}
.decb .n{background:#1b1b1b;color:#fff}
.pick select,.tb .total{background:#fff;border:3px solid #1b1b1b;box-shadow:4px 4px 0 #1b1b1b}
.zoom{border:3px solid #1b1b1b;box-shadow:4px 4px 0 #1b1b1b}
"""
for name, t in T.items():
    out = snap.replace("</head>", f"<style>{STATIC}{t}</style></head>")
    io.open(here / f"{name}.html", "w", encoding="utf-8").write(out)
    print(name, len(out))

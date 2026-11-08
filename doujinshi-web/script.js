const personajes = [
  { nombre: "Haru", rol: "Protagonista", color: "#e0527a", icono: "🌸", texto: "Callada y observadora. Dibuja en su cuaderno lo que no se atreve a decir." },
  { nombre: "Mio", rol: "La amiga que se va", color: "#4a8fe0", icono: "🌊", texto: "Alegre y decidida, esconde su miedo al cambio tras una sonrisa." },
  { nombre: "Abuela Sato", rol: "Guardiana del río", color: "#e0a24a", icono: "🏮", texto: "Conoce todas las historias de las luciérnagas del pueblo." },
];

// Sustituye `texto` por `img: "paginas/01.jpg"` para usar páginas reales.
const paginas = [
  { texto: "Portada\nLuciérnagas de Medianoche" },
  { texto: "Pág. 1 — «Este es el último verano.»" },
  { texto: "Pág. 2 — Haru y Mio cruzan el puente." },
  { texto: "Pág. 3 — Helado derretido, risas." },
  { texto: "Pág. 4 — Las primeras luces sobre el agua." },
  { texto: "Pág. 5 — «Prométeme que volverás.»" },
  { texto: "Contraportada\nGracias por leer" },
];

const $ = (s) => document.querySelector(s);

$("#cards").innerHTML = personajes.map((p) => `
  <article class="card">
    <div class="avatar" style="background:${p.color}">${p.icono}</div>
    <h3>${p.nombre}</h3><strong>${p.rol}</strong>
    <p>${p.texto}</p>
  </article>`).join("");

let actual = 0;
function mostrar() {
  const p = paginas[actual];
  $("#pagina").innerHTML = p.img
    ? `<img src="${p.img}" alt="Página ${actual}" style="max-width:100%">`
    : p.texto.replace(/\n/g, "<br>");
  $("#contador").textContent = `${actual + 1} / ${paginas.length}`;
  $("#sig").disabled = actual === paginas.length - 1;
  $("#ant").disabled = actual === 0;
}
$("#sig").onclick = () => { if (actual < paginas.length - 1) { actual++; mostrar(); } };
$("#ant").onclick = () => { if (actual > 0) { actual--; mostrar(); } };
// Manga: derecha a izquierda → flecha izquierda avanza.
addEventListener("keydown", (e) => {
  if (e.key === "ArrowLeft") $("#sig").click();
  if (e.key === "ArrowRight") $("#ant").click();
});
mostrar();

const raiz = document.documentElement;
try { raiz.dataset.tema = localStorage.getItem("tema") || "claro"; } catch { raiz.dataset.tema = "claro"; }
$("#tema").onclick = () => {
  raiz.dataset.tema = raiz.dataset.tema === "oscuro" ? "claro" : "oscuro";
  try { localStorage.setItem("tema", raiz.dataset.tema); } catch {}
};

$("#form").onsubmit = (e) => {
  e.preventDefault();
  $("#gracias").hidden = false;
  e.target.reset();
};

// Descarga la planilla diaria de determinantes (ANPYN, Santa Fe-Océano) y escribe determinantes.json.
import { writeFileSync, readFileSync, existsSync } from "node:fs";
import { getDocument } from "pdfjs-dist/legacy/build/pdf.mjs";
import { interpretar } from "./det_parse.mjs";

const base = "https://www.argentina.gob.ar/sites/default/files/2025/03/";
const hoy = new Date(Date.now() - 3 * 3600e3); // hora argentina
const hoyTxt = hoy.toISOString().slice(0, 10);
if (existsSync("determinantes.json") && JSON.parse(readFileSync("determinantes.json", "utf8")).fuente?.includes(hoyTxt)) { console.log("Planilla de hoy ya guardada"); process.exit(0); }
async function bajar() {
  for (let d = 0; d < 6; d++) {
    const f = new Date(hoy - d * 864e5).toISOString().slice(0, 10), url = `${base}${f}_sfo.pdf`;
    const r = await fetch(url, { headers: { "User-Agent": "vnt-parana (github.com/btzdev/vnt-parana)" } });
    if (r.ok) return { url, buf: new Uint8Array(await r.arrayBuffer()) };
  }
  throw new Error("No se encontró la planilla de los últimos 6 días");
}
const { url, buf } = await bajar();
const doc = await getDocument({ data: buf, useSystemFonts: true }).promise, lineas = [];
for (let p = 1; p <= doc.numPages; p++) {
  const tc = await (await doc.getPage(p)).getTextContent(), filas = {};
  for (const it of tc.items) { const y = Math.round(it.transform[5]); (filas[y] ||= []).push([it.transform[4], it.str]); }
  lineas.push(...Object.keys(filas).sort((a, b) => b - a).map(y => filas[y].sort((a, b) => a[0] - b[0]).map(x => x[1]).join(" | ")));
}
const d = interpretar(lineas);
if (d.tramos.length < 30) throw new Error("Planilla con pocos tramos: " + d.tramos.length);
writeFileSync("determinantes.json", JSON.stringify({ fuente: url, generado: new Date().toISOString(), ...d }));
console.log(d.fecha, d.tramos.length, "tramos");

// Interpreta el texto de la planilla oficial de determinantes (ANPYN, Santa Fe-Océano).
// lineas: filas de texto con celdas separadas por " | " (agrupadas por altura en la página).
export function interpretar(lineas) {
  const num = s => /^-?\d{1,4},\d{1,2}$/.test(s);
  const n = s => +s.replace(",", ".");
  const out = { fecha: null, alturas: {}, tramos: [], notas: [] };
  let rio = "", nombrePend = "", alturaPend = null;
  for (const l of lineas) {
    const c = l.split("|").map(x => x.trim()).filter(Boolean);
    if (!c.length) continue;
    const txt = c.join(" ");
    const f = txt.match(/PROFUNDIDADES M[ÍI]NIMAS D[ÍI]A:\s*(\d{1,2} de \w+ de \d{4})/i);
    if (f) { out.fecha = f[1]; continue; }
    const h = txt.match(/^([A-ZÁÉÍÓÚÑ .]+?) KM (\d+):\s*(-?\d+,\d+)?$/);
    if (h) { const k = h[1].trim(); if (h[3]) out.alturas[k] = { km: +h[2], m: n(h[3]) }; else alturaPend = { k, km: +h[2] }; continue; }
    if (alturaPend && c.length === 1 && num(c[0])) { out.alturas[alturaPend.k] = { km: alturaPend.km, m: n(c[0]) }; alturaPend = null; continue; }
    if (/^R[IÍ]O /.test(txt) && c.length === 1) { rio = txt; nombrePend = ""; continue; }
    if (/^\([A-Z]\) DRAGA/.test(txt) || /DRAGA .* - (OPERANDO|MANTENIMIENTO)/.test(txt)) { out.notas.push(...txt.split(/(?=\([A-Z]\) )/).map(s => s.trim())); continue; }
    if (num(c[0]) && num(c[1])) {
      let i = 2, nom = nombrePend;
      if (!num(c[i])) nom = c[i++];
      const kmc = n(c[i++]), ancho = +c[i++].replace(/\D/g, ""), cero = n(c[i++]);
      let alt = null, efe = null;
      if (num(c[i] || "") && num(c[i + 1] || "")) { alt = n(c[i++]); efe = n(c[i++]); }
      const resto = c.slice(i), rel = resto.length ? resto.pop() : "";
      out.tramos.push({ rio: /SAN MART[IÍ]N/.test(nom) ? "RIO PARANÁ · Canal San Martín" : rio, desde: n(c[0]), hasta: n(c[1]), nom, kmc, ancho, cero, alt, efe, obs: resto.join(" · "), rel });
      nombrePend = ""; continue;
    }
    if (c.length === 1 && !num(c[0]) && /[A-Z]/.test(c[0]) && !/^(KM|DESDE|HASTA|APROX|CR[IÍ]TICO)/.test(c[0])) {
      if (/^(Precauci|M\.?I|MI )/.test(c[0])) out.notas.push(c[0]); else nombrePend = c[0];
    }
  }
  return out;
}

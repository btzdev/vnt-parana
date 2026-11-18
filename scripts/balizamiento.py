"""Genera balizamiento.json para la app VNT Paraná.

Fuentes:
  - SHN, Radioavisos Náuticos (Ríos): novedades de balizamiento y operaciones de dragado vigentes (oficial).
  - OpenStreetMap / OpenSeaMap vía Overpass: posición de boyas y balizas (no oficial, comunitario).

Si una fuente falla, se conserva lo último que se obtuvo de ella.
"""
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "balizamiento.json")
UA = {"User-Agent": "vnt-parana/1.0 (+https://github.com/btzdev/vnt-parana)"}
SHN_URL = "https://www.hidro.gov.ar/nautica/RadioavisosNauticos.asp?op=11"
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
BBOX = (-34.75, -61.30, -27.20, -58.10)  # S, O, N, E: Delta / Río de la Plata superior hasta Confluencia


def bajar(url, data=None, timeout=120):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


# ---------------------------------------------------------------- SHN
NUM = r"(\d{1,4}(?:[.,]\d{1,3})?)"


def num(s):
    return float(s.replace(",", ".")) if s else None


def ruta_de(rio, km):
    r = rio.upper()
    if "PALMAS" in r:
        return "parana_de_las_palmas"
    if "GUAZ" in r:
        return "parana_guazu"
    if any(x in r for x in ("BRAVO", "MINI", "MINÍ", "TALAVERA", "CORONDA")):
        return None
    if any(x in r for x in ("INFERIOR", "MEDIO", "SUPERIOR")) or re.search(r"PARAN[AÁ]\s*$", r):
        if km is not None and km < 232:
            return "parana_de_las_palmas"
        return "parana"
    return None


ESTADOS = [
    (r"FALTA", "falta"), (r"GARREAD", "garreada"), (r"APAGAD", "apagada"), (r"AVERIAD", "averiada"),
    (r"ALTERAD", "alterada"), (r"DERIVA|GARETE", "a la deriva"), (r"REUBICAD", "reubicada"),
    (r"SUMERGID", "sumergida"), (r"MARCA DE TOPE", "sin marca de tope"),
]


def estado_de(txt):
    t = txt.upper()
    for pat, nom in ESTADOS:
        if re.search(pat, t):
            return nom
    return t.strip(" :").lower()


RIO_RE = re.compile(r"R[IÍ]OS?\s+PARAN[AÁ](?:\s+(?:DE LAS PALMAS|GUAZ[UÚ]|INFERIOR|MEDIO|SUPERIOR|MIN[IÍ]|BRAVO))?|PASAJE TALAVERA|R[IÍ]O CORONDA")


def parse_shn(pagina):
    items, dragas = [], []
    partes = re.split(r"<h2[^>]*>", pagina, flags=re.I)[1:]
    for p in partes:
        if "</h2>" not in p.lower():
            continue
        cab, cuerpo = re.split(r"</h2>", p, maxsplit=1, flags=re.I)
        m = re.search(r"(\d+)-(\d{4})\s*-\s*(\d{2})/(\d{2})/(\d{4})", cab)
        if not m:
            continue
        aviso = f"{m.group(1)}-{m.group(2)}"
        fecha = f"{m.group(5)}-{m.group(4)}-{m.group(3)}"
        cuerpo = re.split(r"<br\s*/?>", cuerpo, maxsplit=1, flags=re.I)[0]
        texto = html.unescape(re.sub(r"<[^>]+>", "", cuerpo)).replace("\r", "")
        lineas = [l.strip().strip("*").strip() for l in texto.split("\n")]
        encabezado = " ".join(lineas[:3]).upper()
        if "URUGUAY" in encabezado and "PARAN" not in encabezado:
            continue
        rio = ""
        if "DRAGADO" in texto.upper():
            for l in lineas:
                if RIO_RE.match(l.upper()):
                    rio = l.strip()
                    continue
                d = re.search(r"DRAGA\s+(.+?)\s+OPERANDO\s+DEL\s+KM\s*" + NUM + r"\s+AL\s+(?:KM\s*)?" + NUM, l.upper())
                if d:
                    k1, k2 = num(d.group(2)), num(d.group(3))
                    dragas.append({"draga": d.group(1).title(), "rio": rio.title(), "ruta": ruta_de(rio, min(k1, k2)),
                                   "km": [min(k1, k2), max(k1, k2)], "fecha": fecha, "aviso": aviso})
            continue
        if "BALIZAMIENTO" not in texto.upper():
            continue
        estado = ""
        for l in lineas:
            u = l.upper()
            if not u:
                continue
            mr = RIO_RE.search(u)
            if mr and not re.search(r"\b(BOYA|BALIZA|BOYAR[IÍ]N)\b", u) and mr.start() < 8:
                rio = mr.group(0)
                continue
            if "NOVEDADES DE BALIZAMIENTO" in u:
                continue
            if not re.search(r"\b(BOYA|BALIZA|BOYAR[IÍ]N)\b", u) or re.match(r"^BOYAS ENFILAMIENTO", u):
                if len(u) < 70:
                    estado = u.rstrip(": ").strip()
                continue
            antes, _, despues = u.partition("(")
            kmn = re.search(r"(?:KM|EX)\s*" + NUM, antes)
            km = num(kmn.group(1)) if kmn else None
            obs = None
            mobs = re.search(r"(?:(?:ALTURA|EN|HACIA|AVISTADA|AVISTAMIENTO|OBSERV[OÓ])\s+(?:DE\s+)?(?:EN\s+)?(?:PROGRESIVA\s+)?|\(\s*)KM\s*" + NUM, u[kmn.end():] if kmn else u)
            if mobs:
                obs = num(mobs.group(1))
            if re.search(r"SIN IDENTIF", u) and km is not None and obs is None:
                km, obs = None, km
            if km is None and obs is None:
                continue
            if "RIO CORONDA" in u:
                obs = None
            lado = "babor" if "BABOR" in antes else "estribor" if "ESTRIBOR" in antes else None
            tipo = "baliza" if antes.strip().startswith("BALIZA") else "boya"
            clase = ("lateral" if "LATERAL" in antes else "cardinal" if "CARDINAL" in antes else
                     "peligro aislado" if "PELIGRO" in antes else "especial" if "ESPECIAL" in antes else
                     "orientación" if "ORIENTACION" in antes or "ORIENTACIÓN" in antes else "")
            sen = re.sub(r"\s+", " ", re.sub(r"(?:KM|EX)\s*" + NUM, "", antes)).strip(" .")
            det = re.sub(r"\s+", " ", despues.rstrip(") ")).strip()
            extra = re.sub(r"\s+", " ", antes[kmn.end():]).strip(" .") if kmn else ""
            est = estado_de(estado) if estado else ""
            if extra and not det:
                det = extra
            if re.search(r"SUMERGID|SEMISUMERGID", u) and est in ("averiada", ""):
                est = "sumergida" if "SEMI" not in u else "semisumergida"
            items.append({
                "rio": rio.title(), "ruta": ruta_de(rio, km or obs), "km": km, "km_obs": obs,
                "tipo": tipo, "clase": clase, "lado": lado, "senal": sen.capitalize(),
                "estado": est, "detalle": det.capitalize(), "fecha": fecha, "aviso": aviso,
            })
    return items, dragas


# ---------------------------------------------------------------- OSM
def bajar_osm():
    s, o, n, e = BBOX
    q = (f'[out:json][timeout:180];node["seamark:type"~"^(buoy_|beacon_|light_minor|light_major|light_vessel)"]'
         f"({s},{o},{n},{e});out;")
    ultimo = None
    for url in OVERPASS:
        try:
            txt = bajar(url, data=urllib.parse.urlencode({"data": q}).encode(), timeout=200)
            return json.loads(txt)["elements"], url
        except Exception as ex:  # probar el siguiente espejo
            ultimo = ex
            print("Overpass falló", url, ex, file=sys.stderr)
    raise RuntimeError(f"Overpass sin respuesta: {ultimo}")


def bajar_trazas_osm():
    """Derrotas recomendadas, canales y líneas de navegación cargadas en OpenStreetMap."""
    s, o, n, e = BBOX
    q = (f'[out:json][timeout:180];way["seamark:type"~"^(fairway|recommended_track|navigation_line|dredged_area)$"]'
         f"({s},{o},{n},{e});out geom tags;")
    for url in OVERPASS:
        try:
            els = json.loads(bajar(url, data=urllib.parse.urlencode({"data": q}).encode(), timeout=200))["elements"]
            out = []
            for w in els:
                g = [[round(p["lat"], 5), round(p["lon"], 5)] for p in w.get("geometry", [])]
                if len(g) >= 2:
                    t = w.get("tags", {})
                    out.append({"t": t.get("seamark:type", ""), "n": t.get("seamark:name") or t.get("name") or "", "g": g})
            return out
        except Exception as ex:
            print("Overpass trazas falló", url, ex, file=sys.stderr)
    return None


def compactar_osm(elems):
    out = []
    for e in elems:
        t = e.get("tags", {})
        st = t.get("seamark:type", "")
        col = (t.get(f"seamark:{st}:colour") or "").split(";")
        cat = t.get(f"seamark:{st}:category", "")
        car = t.get("seamark:light:character") or t.get("seamark:light:1:character") or ""
        per = t.get("seamark:light:period") or t.get("seamark:light:1:period") or ""
        grp = t.get("seamark:light:group") or ""
        luz = (car + (f"({grp})" if grp else "") + (f" {per}s" if per else "")).strip()
        out.append([round(e["lat"], 6), round(e["lon"], 6), st, col[0] if col and col[0] else "", cat,
                    (t.get("seamark:name") or t.get("name") or "")[:40], luz, e["id"]])
    out.sort(key=lambda x: (x[0], x[1]))
    return out


# ---------------------------------------------------------------- METAR (SMN)
METAR_IDS = "SAAR,SAAV,SAAP,SADF,SABE,SAEZ,SADP,SAAG,SAAC,SATR,SARC,SARE,SARP,SATG,SAAJ,SADM,SAAU,SAAM"


def bajar_metar():
    url = "https://aviationweather.gov/api/data/metar?format=json&hours=3&ids=" + METAR_IDS
    datos = json.loads(bajar(url, timeout=60))
    ult = {}
    for m in datos:
        i = m.get("icaoId")
        ot = m.get("obsTime")
        if not i or ot is None:
            continue
        t = datetime.fromtimestamp(int(ot), timezone.utc).isoformat(timespec="seconds")
        if i not in ult or t > ult[i]["time"]:
            ult[i] = {"id": i, "name": (m.get("name") or "").split(",")[0], "lat": m.get("lat"), "lon": m.get("lon"),
                      "time": t, "wdir": m.get("wdir"), "wspd": m.get("wspd"), "wgst": m.get("wgst"),
                      "temp": m.get("temp"), "altim": m.get("altim"), "raw": m.get("rawOb")}
    return sorted(ult.values(), key=lambda x: x["id"])


def escribir_meteo():
    ruta = os.path.join(os.path.dirname(SALIDA), "meteo.json")
    try:
        metar = bajar_metar()
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "fuente": "METAR del SMN (aeropuertos) via aviationweather.gov", "metar": metar},
                      f, ensure_ascii=False, separators=(",", ":"))
        print(f"METAR: {len(metar)} estaciones")
    except Exception as ex:
        print("METAR fall\u00f3:", ex, file=sys.stderr)


# ---------------------------------------------------------------- main
def main():
    escribir_meteo()
    previo = {}
    if os.path.exists(SALIDA):
        try:
            with open(SALIDA, encoding="utf-8") as f:
                previo = json.load(f)
        except Exception:
            previo = {}
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")

    shn = previo.get("shn", {"items": [], "dragas": []})
    try:
        items, dragas = parse_shn(bajar(SHN_URL))
        shn = {"ok": True, "consultado": ahora, "url": SHN_URL, "items": items, "dragas": dragas}
        print(f"SHN: {len(items)} novedades, {len(dragas)} dragas")
    except Exception as ex:
        shn = dict(shn, ok=False, error=str(ex)[:300])
        print("SHN falló:", ex, file=sys.stderr)

    osm = previo.get("osm", {"items": []})
    try:
        elems, url = bajar_osm()
        osm = {"ok": True, "consultado": ahora, "fuente": url,
               "campos": ["lat", "lon", "tipo", "color", "categoria", "nombre", "luz", "osm_id"],
               "items": compactar_osm(elems)}
        trazas = bajar_trazas_osm()
        osm["trazas"] = trazas if trazas is not None else previo.get("osm", {}).get("trazas", [])
        print(f"OSM: {len(osm['items'])} señales")
    except Exception as ex:
        osm = dict(osm, ok=False, error=str(ex)[:300])
        print("OSM falló:", ex, file=sys.stderr)

    datos = {"shn": {k: v for k, v in shn.items() if k != "consultado"},
             "osm": {k: v for k, v in osm.items() if k != "consultado"}}
    huella = hashlib.sha1(json.dumps(datos, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if previo.get("huella") == huella:
        print("Sin cambios.")
        return
    shn["consultado"] = shn.get("consultado") or previo.get("shn", {}).get("consultado")
    osm["consultado"] = osm.get("consultado") or previo.get("osm", {}).get("consultado")
    salida = {"generado": ahora, "huella": huella, "shn": shn, "osm": osm,
              "nota": "SHN = oficial (novedades vigentes, ubicadas por km). OSM/OpenSeaMap = posiciones comunitarias, no oficiales."}
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, separators=(",", ":"))
    print("Escrito", SALIDA)


if __name__ == "__main__":
    main()

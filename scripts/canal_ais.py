"""Acumula la traza real del canal a partir de AIS (canal.json).

Escucha las redes AIS comunitarias (OpenSeaFeed y Open Waters) unos minutos en toda la
Vía Navegable Troncal y suma, en una grilla de ~165 m, las posiciones de buques clase A
que navegan a más de 3 nudos. Cada buque cuenta una sola vez por celda y por muestreo.
Los valores decaen lentamente (vida media ~6 días) para seguir los cambios de traza.
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

import websockets

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "..", "canal.json")
S, O, N, E = -34.75, -61.30, -27.20, -58.10
CEL = 0.0015            # grados (~165 m)
SEG = int(os.environ.get("CANAL_SEG", "240"))
DECAE = 0.995           # por muestreo horario
SOG_MIN = 3.0


def celda(lat, lon):
    return f"{int(lat // CEL)}_{int(lon // CEL)}"


async def osf(pos):
    async with websockets.connect("wss://stream.openseafeed.com/v1/stream", open_timeout=20,
                                  max_size=2**22, user_agent_header="vnt-parana/1.0") as ws:
        await ws.send(json.dumps({"BoundingBoxes": [[[S, O], [N, E]]]}))
        fin = time.time() + SEG
        while time.time() < fin:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=max(1, fin - time.time()))
            except asyncio.TimeoutError:
                break
            try:
                j = json.loads(msg)
            except ValueError:
                continue
            if j.get("MessageType") != "PositionReport":
                continue
            m = j["Message"]["PositionReport"]; md = j.get("MetaData", {})
            pos.append((md.get("MMSI") or m.get("UserID"), md.get("latitude", m.get("Latitude")),
                        md.get("longitude", m.get("Longitude")), m.get("Sog"), m.get("Cog")))


async def openwaters(pos):
    async with websockets.connect("wss://ais.openwaters.io/v1/stream", open_timeout=20,
                                  max_size=2**22, user_agent_header="vnt-parana/1.0") as ws:
        await ws.send(json.dumps({"type": "subscribe", "bbox": [[S, O, N, E]], "snapshot": True}))
        fin = time.time() + SEG
        while time.time() < fin:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=max(1, fin - time.time()))
            except asyncio.TimeoutError:
                break
            try:
                j = json.loads(msg)
            except ValueError:
                continue
            if j.get("type") != "event" or j.get("msg_type") != "PositionReport":
                continue
            m = j.get("message", {})
            pos.append((j.get("mmsi"), j.get("lat", m.get("Latitude")), j.get("lon", m.get("Longitude")),
                        m.get("Sog"), m.get("Cog")))


async def escuchar():
    pos = []
    res = await asyncio.gather(osf(pos), openwaters(pos), return_exceptions=True)
    for r in res:
        if isinstance(r, Exception):
            print("AIS:", repr(r)[:200], file=sys.stderr)
    return pos


def main():
    previo = {}
    if os.path.exists(SALIDA):
        try:
            with open(SALIDA, encoding="utf-8") as f:
                previo = json.load(f)
        except Exception:
            previo = {}
    c = {k: v * DECAE for k, v in (previo.get("c") or {}).items()}
    pos = asyncio.run(escuchar())
    vistos = set()
    por_buque = {}
    for mmsi, la, lo, sog, cog in pos:
        if mmsi is None or la is None or lo is None or sog is None:
            continue
        if not (S <= la <= N and O <= lo <= E) or sog < SOG_MIN or sog > 30:
            continue
        por_buque.setdefault(mmsi, []).append((la, lo))
    for mmsi, pts in por_buque.items():
        # interpola entre posiciones consecutivas para no dejar huecos
        for (a1, o1), (a2, o2) in zip(pts, pts[1:] + pts[-1:]):
            pasos = max(1, int(max(abs(a2 - a1), abs(o2 - o1)) / (CEL / 2)))
            if pasos > 40:  # salto grande: no interpolar
                pasos = 1
            for s in range(pasos + 1):
                t = s / pasos
                k = celda(a1 + (a2 - a1) * t, o1 + (o2 - o1) * t)
                if (mmsi, k) not in vistos:
                    vistos.add((mmsi, k))
                    c[k] = c.get(k, 0) + 1
    c = {k: round(v, 2) for k, v in c.items() if v >= 0.05}
    vals = sorted(c.values())
    mx = vals[int(len(vals) * 0.98)] if vals else 1
    salida = {"actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "corridas": int(previo.get("corridas", 0)) + 1, "cel": CEL, "max": round(mx, 2), "umbral": 0.8,
              "buques_ultimo": len(por_buque), "nota": "Densidad de tráfico AIS (buques clase A > 3 kn). No oficial.",
              "c": c}
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(salida, f, separators=(",", ":"))
    print(f"Canal AIS: {len(pos)} posiciones, {len(por_buque)} buques en movimiento, {len(c)} celdas")


if __name__ == "__main__":
    main()

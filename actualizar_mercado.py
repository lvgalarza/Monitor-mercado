#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitor de mercado para principiantes
=====================================
Descarga precios de acciones del S&P 500, ETFs, ETFs de bonos y futuros,
más los rendimientos de los bonos del Tesoro de EE. UU. (FRED), calcula
indicadores sencillos (incluido el resumen de dividendos) y genera un tablero web
autocontenido (docs/index.html).

Uso:
    python actualizar_mercado.py                 # datos reales
    python actualizar_mercado.py --demo          # datos inventados, para probar el diseño
    python actualizar_mercado.py --limite 50     # umbral de precio por defecto en el tablero

Esta herramienta INFORMA; no recomienda comprar ni vender.
"""
import argparse
import datetime as dt
import io
import json
import math
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 1. UNIVERSO DE INSTRUMENTOS (edita estas listas a tu gusto)
# ---------------------------------------------------------------------------
ETFS = {
    "SPLG": ("SPDR Portfolio S&P 500", "S&P 500 (500 empresas grandes de EE. UU.)"),
    "SPY": ("SPDR S&P 500", "S&P 500 (500 empresas grandes de EE. UU.)"),
    "VOO": ("Vanguard S&P 500", "S&P 500 (500 empresas grandes de EE. UU.)"),
    "QQQ": ("Invesco Nasdaq 100", "Nasdaq 100 (tecnológicas grandes)"),
    "DIA": ("SPDR Dow Jones", "Dow Jones (30 empresas)"),
    "IWM": ("iShares Russell 2000", "Empresas pequeñas de EE. UU."),
    "VTI": ("Vanguard Total Market", "Todo el mercado de EE. UU."),
    "SCHB": ("Schwab U.S. Broad Market", "Todo el mercado de EE. UU."),
    "VT": ("Vanguard Total World", "Mercado mundial"),
    "VXUS": ("Vanguard Total Intl", "Mercados fuera de EE. UU."),
    "VEA": ("Vanguard Developed Markets", "Países desarrollados (sin EE. UU.)"),
    "VWO": ("Vanguard Emerging Markets", "Países emergentes"),
    "SCHD": ("Schwab U.S. Dividend", "Empresas que pagan dividendos"),
    "VYM": ("Vanguard High Dividend", "Empresas que pagan dividendos"),
    "VIG": ("Vanguard Dividend Growth", "Dividendos crecientes"),
    "XLK": ("Sector Tecnología", "Sector"), "XLF": ("Sector Financiero", "Sector"),
    "XLE": ("Sector Energía", "Sector"), "XLV": ("Sector Salud", "Sector"),
    "XLU": ("Sector Servicios públicos", "Sector"), "XLP": ("Sector Consumo básico", "Sector"),
    "XLI": ("Sector Industrial", "Sector"), "XLY": ("Sector Consumo discrecional", "Sector"),
    "VNQ": ("Vanguard Real Estate", "Inmobiliario"),
    "GLD": ("SPDR Gold (oro)", "Materias primas"), "IAU": ("iShares Gold (oro)", "Materias primas"),
    "SLV": ("iShares Silver (plata)", "Materias primas"), "USO": ("United States Oil (petróleo)", "Materias primas"),
}

BONOS_ETF = {
    "BND": ("Vanguard Total Bond Market", "Bonos de EE. UU. (mixto)"),
    "AGG": ("iShares Core US Aggregate Bond", "Bonos de EE. UU. (mixto)"),
    "BIL": ("SPDR Bloomberg 1-3 Month T-Bill", "Letras del Tesoro (muy corto plazo)"),
    "SGOV": ("iShares 0-3 Month Treasury", "Letras del Tesoro (muy corto plazo)"),
    "SHY": ("iShares 1-3 Year Treasury", "Tesoro corto plazo"),
    "VGSH": ("Vanguard Short-Term Treasury", "Tesoro corto plazo"),
    "IEI": ("iShares 3-7 Year Treasury", "Tesoro mediano plazo"),
    "IEF": ("iShares 7-10 Year Treasury", "Tesoro mediano plazo"),
    "TLT": ("iShares 20+ Year Treasury", "Tesoro largo plazo (más volátil)"),
    "TIP": ("iShares TIPS Bond", "Bonos protegidos contra inflación"),
    "LQD": ("iShares Investment Grade Corp", "Bonos corporativos sólidos"),
    "VCSH": ("Vanguard Short-Term Corporate", "Corporativos corto plazo"),
    "BSV": ("Vanguard Short-Term Bond", "Bonos corto plazo"),
    "HYG": ("iShares High Yield Corp", "Bonos corporativos de mayor riesgo"),
    "EMB": ("iShares Emerging Markets Bond", "Bonos de países emergentes"),
    "MUB": ("iShares National Muni Bond", "Bonos municipales de EE. UU."),
}

# símbolo: (nombre, multiplicador del contrato, divisor del precio, unidad del contrato)
FUTUROS = {
    "ES=F": ("E-mini S&P 500", 50, 1, "50 × índice"),
    "NQ=F": ("E-mini Nasdaq 100", 20, 1, "20 × índice"),
    "YM=F": ("E-mini Dow Jones", 5, 1, "5 × índice"),
    "GC=F": ("Oro", 100, 1, "100 onzas"),
    "SI=F": ("Plata", 5000, 1, "5.000 onzas"),
    "HG=F": ("Cobre", 25000, 1, "25.000 libras"),
    "CL=F": ("Petróleo WTI", 1000, 1, "1.000 barriles"),
    "NG=F": ("Gas natural", 10000, 1, "10.000 MMBtu"),
    "ZC=F": ("Maíz", 5000, 100, "5.000 bushels"),
    "ZW=F": ("Trigo", 5000, 100, "5.000 bushels"),
    "ZS=F": ("Soya", 5000, 100, "5.000 bushels"),
    "ZN=F": ("Nota del Tesoro 10 años", 1000, 1, "US$ 1.000 × precio"),
    "ZB=F": ("Bono del Tesoro 30 años", 1000, 1, "US$ 1.000 × precio"),
}

FRED = {
    "DGS3MO": "Letras 3 meses",
    "DGS2": "Bono 2 años",
    "DGS5": "Bono 5 años",
    "DGS10": "Bono 10 años",
    "DGS30": "Bono 30 años",
}

SECTORES = {
    "Information Technology": "Tecnología", "Health Care": "Salud", "Financials": "Finanzas",
    "Consumer Discretionary": "Consumo discrecional", "Communication Services": "Comunicaciones",
    "Industrials": "Industria", "Consumer Staples": "Consumo básico", "Energy": "Energía",
    "Utilities": "Servicios públicos", "Real Estate": "Inmobiliario", "Materials": "Materiales",
}

# Lista de respaldo si Wikipedia no responde (la lista completa se obtiene en línea).
RESPALDO_SP500 = {
    "AAPL": ("Apple", "Tecnología"), "MSFT": ("Microsoft", "Tecnología"), "NVDA": ("Nvidia", "Tecnología"),
    "INTC": ("Intel", "Tecnología"), "CSCO": ("Cisco", "Tecnología"), "ORCL": ("Oracle", "Tecnología"),
    "GOOGL": ("Alphabet", "Comunicaciones"), "META": ("Meta Platforms", "Comunicaciones"),
    "T": ("AT&T", "Comunicaciones"), "VZ": ("Verizon", "Comunicaciones"), "DIS": ("Walt Disney", "Comunicaciones"),
    "AMZN": ("Amazon", "Consumo discrecional"), "F": ("Ford", "Consumo discrecional"),
    "GM": ("General Motors", "Consumo discrecional"), "NKE": ("Nike", "Consumo discrecional"),
    "MCD": ("McDonald's", "Consumo discrecional"), "HD": ("Home Depot", "Consumo discrecional"),
    "KO": ("Coca-Cola", "Consumo básico"), "PEP": ("PepsiCo", "Consumo básico"), "PG": ("Procter & Gamble", "Consumo básico"),
    "WMT": ("Walmart", "Consumo básico"), "MO": ("Altria", "Consumo básico"), "KHC": ("Kraft Heinz", "Consumo básico"),
    "JNJ": ("Johnson & Johnson", "Salud"), "PFE": ("Pfizer", "Salud"), "MRK": ("Merck", "Salud"),
    "JPM": ("JPMorgan Chase", "Finanzas"), "BAC": ("Bank of America", "Finanzas"), "WFC": ("Wells Fargo", "Finanzas"),
    "C": ("Citigroup", "Finanzas"), "XOM": ("Exxon Mobil", "Energía"), "CVX": ("Chevron", "Energía"),
    "KMI": ("Kinder Morgan", "Energía"), "O": ("Realty Income", "Inmobiliario"), "DOW": ("Dow Inc.", "Materiales"),
    "NEM": ("Newmont", "Materiales"), "FCX": ("Freeport-McMoRan", "Materiales"), "DAL": ("Delta Air Lines", "Industria"),
    "CSX": ("CSX", "Industria"), "GE": ("GE Aerospace", "Industria"), "DUK": ("Duke Energy", "Servicios públicos"),
    "SO": ("Southern Company", "Servicios públicos"), "NEE": ("NextEra Energy", "Servicios públicos"),
}


def sp500():
    """Lista actual del S&P 500 desde Wikipedia (con respaldo)."""
    try:
        import requests
        r = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0 (monitor-mercado; uso personal)"}, timeout=30)
        r.raise_for_status()
        tabla = pd.read_html(io.StringIO(r.text))[0]
        out = {}
        for _, f in tabla.iterrows():
            simbolo = str(f["Symbol"]).replace(".", "-").strip()
            out[simbolo] = (str(f["Security"]), SECTORES.get(f["GICS Sector"], f["GICS Sector"]))
        if len(out) > 400:
            return out
    except Exception as e:  # noqa: BLE001
        print(f"[aviso] No pude leer la lista del S&P 500 ({e}). Uso lista de respaldo.", file=sys.stderr)
    return dict(RESPALDO_SP500)


def construir_universo():
    u = {}
    for t, (n, s) in sp500().items():
        u[t] = {"n": n, "cat": "Acción", "sec": s}
    for t, (n, s) in ETFS.items():
        u[t] = {"n": n, "cat": "ETF", "sec": s}
    for t, (n, s) in BONOS_ETF.items():
        u[t] = {"n": n, "cat": "Bono", "sec": s}
    for t, (n, m, d, unidad) in FUTUROS.items():
        u[t] = {"n": n, "cat": "Futuro", "sec": "Futuros", "mult": m, "div": d, "unidad": unidad}
    return u


# ---------------------------------------------------------------------------
# 2. DESCARGA DE DATOS
# ---------------------------------------------------------------------------
def descargar_precios(tickers, periodo="2y", lote=80):
    import yfinance as yf
    marcos = {}
    for i in range(0, len(tickers), lote):
        grupo = tickers[i:i + lote]
        try:
            df = yf.download(grupo, period=periodo, interval="1d", auto_adjust=True,
                             actions=True,  # incluye la columna "Dividends"
                             group_by="ticker", threads=True, progress=False)
        except Exception as e:  # noqa: BLE001
            print(f"[aviso] Falló un lote de descarga: {e}", file=sys.stderr)
            continue
        niveles = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else []
        for t in grupo:
            try:
                sub = df[t] if t in niveles else (df if len(grupo) == 1 else None)
                if sub is None:
                    continue
                sub = sub.dropna(subset=["Close"])
                if len(sub) >= 30:
                    marcos[t] = sub
            except Exception:  # noqa: BLE001
                continue
        print(f"  descargados {min(i + lote, len(tickers))}/{len(tickers)}")
    return marcos


def descargar_fundamentales(tickers, max_seg=420):
    """P/E, rendimiento por dividendo y tamaño. Es lento; se limita el tiempo total."""
    import yfinance as yf
    t0 = time.time()

    def uno(t):
        if time.time() - t0 > max_seg:
            return t, {}
        try:
            i = yf.Ticker(t).info or {}
            pe = i.get("trailingPE")
            dv = i.get("trailingAnnualDividendYield")
            return t, {
                "pe": round(float(pe), 1) if pe and pe > 0 else None,
                "div": round(float(dv) * 100, 2) if dv else None,
                "cap": i.get("marketCap"),
            }
        except Exception:  # noqa: BLE001
            return t, {}

    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(ex.map(uno, tickers))


def descargar_rendimientos():
    out = []
    for sid, nombre in FRED.items():
        try:
            df = pd.read_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}")
            df.columns = ["fecha", "valor"]
            df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
            s = df.dropna().tail(300)["valor"].reset_index(drop=True)
            out.append(armar_rendimiento(sid, nombre, s))
        except Exception as e:  # noqa: BLE001
            print(f"[aviso] No pude leer {sid} de FRED: {e}", file=sys.stderr)
    return out


def armar_rendimiento(sid, nombre, s):
    ult, ant = float(s.iloc[-1]), float(s.iloc[-2])
    return {
        "id": sid, "nombre": nombre, "valor": round(ult, 2),
        "cambio_pb": round((ult - ant) * 100, 0),
        "hace_1m": round(float(s.iloc[-22]), 2) if len(s) > 22 else None,
        "hace_1a": round(float(s.iloc[-252]), 2) if len(s) > 252 else None,
    }


def texto_curva(rend):
    v = {r["id"]: r["valor"] for r in rend}
    if "DGS10" not in v or "DGS2" not in v:
        return None
    sp = round(v["DGS10"] - v["DGS2"], 2)
    if sp < 0:
        txt = ("Curva invertida: hoy los bonos de 2 años pagan más que los de 10. Históricamente ha "
               "coincidido con periodos previos a desaceleraciones, pero no es una predicción segura.")
    else:
        txt = ("Curva normal: los bonos de más plazo pagan más que los cortos, "
               "que es la situación habitual cuando la economía no da señales de tensión.")
    return {"spread": sp, "texto": txt}


# ---------------------------------------------------------------------------
# 3. INDICADORES Y PUNTAJE
# ---------------------------------------------------------------------------
def r(x, d=2):
    if x is None:
        return None
    try:
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return None
        return round(float(x), d)
    except (TypeError, ValueError):
        return None


def calc_rsi(c, n=14):
    d = c.diff().dropna()
    if len(d) < n + 1:
        return None
    ganancia = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    perdida = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    if perdida.iloc[-1] == 0:
        return 100.0
    rs = ganancia.iloc[-1] / perdida.iloc[-1]
    return float(100 - 100 / (1 + rs))


def variacion(c, n):
    return (c.iloc[-1] / c.iloc[-1 - n] - 1) * 100 if len(c) > n else None


def dividendos(sub, precio):
    """Resumen de dividendos a partir del historial de Yahoo (columna 'Dividends').
    Devuelve None si no pagó dividendos en los últimos 12 meses."""
    if "Dividends" not in sub.columns or not precio:
        return None
    idx = pd.DatetimeIndex(sub.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    d = pd.Series(pd.to_numeric(sub["Dividends"], errors="coerce").fillna(0.0).values, index=idx)
    d = d[d > 0]
    if d.empty:
        return None
    fin = idx[-1]
    ult12 = d[d.index > fin - pd.Timedelta(days=365)]
    if ult12.empty:
        return None
    huecos = d.index.to_series().diff().dt.days.dropna()
    mediana = float(huecos.tail(6).median()) if len(huecos) else None
    if mediana is None:
        frec, n_anio = "Anual o irregular", 1
    elif mediana < 45:
        frec, n_anio = "Mensual", 12
    elif mediana < 121:
        frec, n_anio = "Trimestral", 4
    elif mediana < 241:
        frec, n_anio = "Semestral", 2
    elif mediana < 451:
        frec, n_anio = "Anual", 1
    else:
        frec, n_anio = "Irregular", None
    pagos = ult12.tail(n_anio) if n_anio and len(ult12) > n_anio else ult12
    anual = float(pagos.sum())
    prox = None
    if mediana and frec != "Irregular":
        est = d.index[-1] + pd.Timedelta(days=int(round(mediana)))
        if est > fin:
            prox = est.strftime("%Y-%m-%d")
    return {
        "anual": r(anual, 4),                       # US$ por acción en los últimos 12 meses
        "pct": r(anual / precio * 100, 2),          # rendimiento por dividendo (%)
        "frec": frec,                               # forma de pago: Mensual, Trimestral...
        "n": int(n_anio or len(pagos)),             # pagos por año
        "ult": r(float(d.iloc[-1]), 4),             # último pago (US$ por acción)
        "ult_f": d.index[-1].strftime("%Y-%m-%d"),  # fecha ex-dividendo del último pago
        "prox": prox,                               # próxima fecha estimada
    }


def indicadores(sub):
    c = sub["Close"].astype(float)
    ult = float(c.iloc[-1])
    anio = c.index[-1].year
    previos = c[c.index.year < anio]
    base_ytd = float(previos.iloc[-1]) if len(previos) else float(c.iloc[0])
    ult252 = c.tail(252)
    hi, lo = float(ult252.max()), float(ult252.min())
    vol = c.pct_change().dropna().tail(90).std() * math.sqrt(252) * 100
    return {
        "p": ult,
        "d1": variacion(c, 1), "d5": variacion(c, 5), "m1": variacion(c, 21),
        "m3": variacion(c, 63), "ytd": (ult / base_ytd - 1) * 100,
        "a1": variacion(c, 251) if len(c) > 251 else None,
        "hi": hi, "lo": lo, "dh": (ult / hi - 1) * 100,
        "s50": float(c.tail(50).mean()) if len(c) >= 50 else None,
        "s200": float(c.tail(200).mean()) if len(c) >= 200 else None,
        "vol": float(vol) if not np.isnan(vol) else None,
        "rsi": calc_rsi(c),
        "spark": [round(float(x), 2) for x in c.tail(60)],
        "fecha": str(c.index[-1].date()),
        "dv": dividendos(sub, ult),
    }


def puntuar(m):
    """Puntaje 0-100 con reglas transparentes. Devuelve (puntaje, semáforo, riesgo, a favor, en contra)."""
    pts, pos, neg = 0, [], []
    p, s50, s200, vol, rsi, dh, a1 = (m.get(k) for k in ("p", "s50", "s200", "vol", "rsi", "dh", "a1"))

    if s200 is not None:
        if p > s200:
            pts += 25; pos.append("Cotiza por encima de su promedio de 200 días: la tendencia de largo plazo es al alza.")
        else:
            neg.append("Cotiza por debajo de su promedio de 200 días: la tendencia de largo plazo es a la baja.")
    if s50 is not None:
        if p > s50:
            pts += 10; pos.append("Está sobre su promedio de 50 días: el último tramo es favorable.")
        else:
            neg.append("Está bajo su promedio de 50 días: el último tramo es débil.")
    if s50 is not None and s200 is not None and s50 > s200:
        pts += 10; pos.append("Su promedio de 50 días supera al de 200: las tendencias corta y larga coinciden.")

    riesgo = "Alto"
    if vol is not None:
        if vol < 20:
            pts += 20; riesgo = "Bajo"; pos.append(f"Se mueve poco (volatilidad anual {vol:.0f} %): historial más tranquilo.")
        elif vol < 35:
            pts += 10; riesgo = "Medio"
        else:
            neg.append(f"Se mueve mucho (volatilidad anual {vol:.0f} %): puede subir o bajar con fuerza en pocos días.")
    if rsi is not None:
        if 40 <= rsi <= 65:
            pts += 15; pos.append(f"Ritmo equilibrado (RSI {rsi:.0f}): ni sobrecomprado ni sobrevendido.")
        elif 65 < rsi <= 75:
            pts += 8
        elif rsi > 75:
            neg.append(f"Subió muy rápido (RSI {rsi:.0f}): con frecuencia viene una pausa o corrección.")
        elif rsi < 30:
            pts += 5; neg.append(f"Cayó con fuerza (RSI {rsi:.0f}): puede rebotar o seguir cayendo; averigua el motivo.")
        else:
            pts += 8
    if dh is not None:
        if dh > -10:
            pts += 10; pos.append("Está cerca de su máximo de 52 semanas.")
        elif dh > -25:
            pts += 5
        elif dh < -40:
            neg.append(f"Está {abs(dh):.0f} % por debajo de su máximo anual: investiga por qué cayó antes de decidir.")
    if a1 is not None:
        if a1 > 0:
            pts += 10; pos.append("Ganó valor en el último año.")
        else:
            neg.append("Perdió valor en el último año.")

    sem = "verde" if pts >= 70 else "amarillo" if pts >= 45 else "rojo"
    return pts, sem, riesgo, pos, neg


# ---------------------------------------------------------------------------
# 4. DATOS DE DEMOSTRACIÓN (solo para probar el diseño)
# ---------------------------------------------------------------------------
def marcos_demo(tickers):
    rnd = np.random.default_rng(7)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=320)
    marcos = {}
    for t in tickers:
        p0 = float(np.exp(rnd.uniform(math.log(8), math.log(650))))
        mu = rnd.normal(0.0003, 0.0004)
        sg = rnd.uniform(0.005, 0.028)
        c = p0 * np.exp(np.cumsum(rnd.normal(mu, sg, len(idx))))
        div = np.zeros(len(idx))
        if "=F" not in t and rnd.random() < 0.65:
            paso = int(rnd.choice([21, 63, 63, 63, 126, 252]))
            rend = rnd.uniform(0.004, 0.06)
            for k in range(int(rnd.integers(5, paso)), len(idx), paso):
                div[k] = p0 * rend * paso / 252
        marcos[t] = pd.DataFrame({"Close": c, "Volume": 1e6, "Dividends": div}, index=idx)
    return marcos


def rendimientos_demo():
    base = {"DGS3MO": 4.1, "DGS2": 3.9, "DGS5": 3.95, "DGS10": 4.2, "DGS30": 4.8}
    out = []
    for sid, nombre in FRED.items():
        s = pd.Series([base[sid] + 0.15 * math.sin(i / 20) for i in range(300)])
        out.append(armar_rendimiento(sid, nombre, s))
    return out


# ---------------------------------------------------------------------------
# 5. PROGRAMA PRINCIPAL
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="usar datos inventados")
    ap.add_argument("--limite", type=float, default=100.0, help="umbral de precio por defecto (US$)")
    ap.add_argument("--salida", default=os.path.join(AQUI, "docs"))
    ap.add_argument("--sin-fundamentales", action="store_true")
    args = ap.parse_args()

    print("1/5 Construyendo lista de instrumentos...")
    universo = construir_universo()
    if args.demo:
        universo = {t: v for t, v in universo.items() if v["cat"] != "Acción" or t in RESPALDO_SP500}
    print(f"    {len(universo)} instrumentos")

    print("2/5 Descargando precios...")
    marcos = marcos_demo(list(universo)) if args.demo else descargar_precios(list(universo))
    if len(marcos) < 20:
        sys.exit("Error: se descargaron muy pocos precios. No se actualiza el tablero.")

    print("3/5 Calculando indicadores...")
    filas = []
    for t, sub in marcos.items():
        meta = universo[t]
        try:
            m = indicadores(sub)
        except Exception as e:  # noqa: BLE001
            print(f"[aviso] {t}: {e}", file=sys.stderr)
            continue
        fila = {"t": t.replace("=F", ""), "n": meta["n"], "cat": meta["cat"], "sec": meta["sec"]}
        if meta["cat"] == "Futuro":
            fila["sem"], fila["score"], fila["pos"], fila["neg"] = "gris", None, [], []
            fila["riesgo"] = "Muy alto"
            fila["contrato"] = round(m["p"] / meta["div"] * meta["mult"])
            fila["unidad"] = meta["unidad"]
        else:
            fila["score"], fila["sem"], fila["riesgo"], fila["pos"], fila["neg"] = puntuar(m)
        for k, d in (("p", 2), ("d1", 2), ("d5", 2), ("m1", 2), ("m3", 2), ("ytd", 2), ("a1", 2),
                     ("hi", 2), ("lo", 2), ("dh", 1), ("s50", 2), ("s200", 2), ("vol", 1), ("rsi", 0)):
            fila[k] = r(m[k], d)
        fila["spark"] = m["spark"]
        fila["fecha"] = m["fecha"]
        fila["dv"] = None if meta["cat"] == "Futuro" else m["dv"]
        filas.append(fila)

    print("4/5 Obteniendo P/E y dividendos (instrumentos bajo el umbral)...")
    candidatos = [f["t"] for f in filas
                  if f["cat"] in ("Acción", "ETF") and f["p"] is not None and f["p"] <= max(args.limite, 100)]
    if args.demo:
        rnd = random.Random(3)
        fund = {t: {"pe": round(rnd.uniform(8, 40), 1), "div": round(rnd.uniform(0, 4), 2)} for t in candidatos}
    elif args.sin_fundamentales:
        fund = {}
    else:
        fund = descargar_fundamentales(candidatos)
    for f in filas:
        extra = fund.get(f["t"], {})
        f["pe"], f["div"] = extra.get("pe"), extra.get("div")

    print("5/5 Rendimientos de bonos y generación del tablero...")
    rend = rendimientos_demo() if args.demo else descargar_rendimientos()
    zona = dt.timezone(dt.timedelta(hours=-5))
    datos = {
        "generado": dt.datetime.now(zona).strftime("%d/%m/%Y %H:%M") + " (hora de Ecuador)",
        "fecha_mercado": max(f["fecha"] for f in filas),
        "demo": bool(args.demo),
        "umbral": args.limite,
        "rendimientos": rend,
        "curva": texto_curva(rend),
        "instrumentos": filas,
    }
    os.makedirs(args.salida, exist_ok=True)
    with open(os.path.join(AQUI, "plantilla.html"), encoding="utf-8") as fh:
        plantilla = fh.read()
    cuerpo = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    html = plantilla.replace("__DATOS_JSON__", cuerpo.replace("</", "<\\/"))
    with open(os.path.join(args.salida, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    with open(os.path.join(args.salida, "datos.json"), "w", encoding="utf-8") as fh:
        fh.write(cuerpo)
    print(f"Listo: {len(filas)} instrumentos -> {os.path.join(args.salida, 'index.html')}")


if __name__ == "__main__":
    main()

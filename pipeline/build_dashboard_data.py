"""
Genera dashboard_data.js con dataset fila-por-usuario, columnar y con
dictionary-encoding (enteros chicos) para que el dashboard pueda filtrar
con precision exacta por cualquier combinacion de dimensiones, incluyendo
destino especifico (4600+ valores) y fecha_comunicar exacta (dia a dia).
"""

import pandas as pd
import numpy as np
import json
import os
import sys

sys.path.insert(0, r"C:\xampp\htdocs\MKTBI\2nd_rebuy\pipeline")
from clasificar_destinos import TIPO_DESTINO

CSV     = r"C:\xampp\htdocs\MKTBI\2nd_rebuy\Outputs\recomendaciones_knn_v3.csv"
PARQUET = r"C:\xampp\htdocs\MKTBI\2nd_rebuy\Outputs\usuarios_features_knn.parquet"
OUT_JS  = r"C:\xampp\htdocs\MKTBI\2nd_rebuy\Outputs\dashboard_data.js"

EPOCH = pd.Timestamp("2022-01-01")

print("Cargando CSV...")
df = pd.read_csv(CSV)
print(f"  {len(df):,} filas")

if "origen_trip" not in df.columns:
    print("Agregando origen_trip (1er viaje) desde el parquet (compatibilidad con CSVs viejos)...")
    origen_df = pd.read_parquet(PARQUET, columns=["social_id", "origen_trip"])
    df = df.merge(origen_df, on="social_id", how="left")
df["origen_trip"] = df["origen_trip"].fillna("Sin dato")

# ── producto_main (vectorizado) ───────────────────────────────────────────────
p = df["producto_recomendado"].fillna("")
vuelos   = p.str.contains("Vuelos", na=False)
hoteles  = p.str.contains("Hoteles", na=False)
df["producto_main"] = np.select(
    [
        vuelos & hoteles,
        vuelos,
        hoteles,
        p.str.contains("Traslados", na=False),
        p.str.contains("Asistencia", na=False),
        p.str.contains("Excursiones", na=False),
        p.str.contains("Autos", na=False),
        p.str.contains("Universal", na=False),
    ],
    [
        "Paquete (Vuelos+Hoteles)", "Vuelos", "Hoteles", "Traslados",
        "Asistencia al viajero", "Excursiones", "Autos", "Universal",
    ],
    default="Otro",
)

# ── encoding helper ────────────────────────────────────────────────────────────
def cat_encode(series, order=None, fillval="Sin dato"):
    s = series.fillna(fillval).astype(str)
    if order:
        cat = pd.Categorical(s, categories=order)
        # cualquier valor fuera del orden esperado cae a NaN -> lo mandamos a fillval
        if cat.codes.min() < 0:
            s = s.where(s.isin(order), fillval)
            cat = pd.Categorical(s, categories=order)
    else:
        cat = pd.Categorical(s)
    return cat.codes.astype(int).tolist(), list(cat.categories)

print("Codificando dimensiones...")
pais_codes, pais_cats           = cat_encode(df["pais"])
tviaje_codes, tviaje_cats       = cat_encode(df["tipo_viaje"])
income_codes, income_cats       = cat_encode(
    df["income"], order=["Unknown", "Low", "Medium", "High"]
)
edad_codes, edad_cats           = cat_encode(
    df["rango_edad_primer_trip"],
    order=["Sin dato", "<18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+", "Edad invalida"],
)
prod_codes, prod_cats           = cat_encode(df["producto_main"])
tipo_dest_codes, tipo_dest_cats = cat_encode(df["tipo_destino_recomendado"])

# destino especifico + su tipo_destino "dominante" (para agrupar el arbol)
dest_fill = df["destino_recomendado"].fillna("SIN_DATO").astype(str)
dest_cat  = pd.Categorical(dest_fill)
dest_codes = dest_cat.codes.astype(int).tolist()
dest_cats  = list(dest_cat.categories)

print("  Calculando tipo dominante por destino...")
tmp = pd.DataFrame({"d": dest_fill, "t": tipo_dest_codes})
dest_to_tipo_map = tmp.groupby("d")["t"].agg(lambda s: s.value_counts().idxmax())
dest_tipo_idx = [int(dest_to_tipo_map[c]) for c in dest_cats]

# origen del primer viaje + su tipo (misma taxonomia de clasificar_destinos.py)
def clasificar_origen(v):
    if v == "Sin vuelo":
        return "SIN_VUELO"
    return TIPO_DESTINO.get(v, "OTRO")

df["tipo_origen"] = df["origen_trip"].apply(clasificar_origen)
tipo_origen_codes, tipo_origen_cats = cat_encode(df["tipo_origen"])

origen_fill = df["origen_trip"].astype(str)
origen_cat  = pd.Categorical(origen_fill)
origen_codes = origen_cat.codes.astype(int).tolist()
origen_cats  = list(origen_cat.categories)

print("  Calculando tipo dominante por origen...")
tmp2 = pd.DataFrame({"o": origen_fill, "t": tipo_origen_codes})
origen_to_tipo_map = tmp2.groupby("o")["t"].agg(lambda s: s.value_counts().idxmax())
origen_tipo_idx = [int(origen_to_tipo_map[c]) for c in origen_cats]

# ── numericas ──────────────────────────────────────────────────────────────────
conf_int    = (df["confianza"] * 100).round().fillna(0).astype(int).tolist()
dias_antic  = df["dias_anticipacion_compra_2"].fillna(-1).round().astype(int).tolist()
dias_timing = df["dias_checkout_a_compra_2"].fillna(-1).round().astype(int).tolist()

fecha = pd.to_datetime(df["fecha_comunicar"], errors="coerce")
fecha_day = (fecha - EPOCH).dt.days.fillna(-1).astype(int).tolist()

gb = df["gross_bookings_usd"].fillna(0).round().astype(int).tolist()

print(f"  Destinos unicos: {len(dest_cats):,}")
print(f"  Origenes unicos: {len(origen_cats):,}")
print(f"  Dias unicos (excl. null): {len(set(d for d in fecha_day if d >= 0)):,}")

# ── empaquetar ─────────────────────────────────────────────────────────────────
output = {
    "meta": {
        "total_usuarios": len(df),
        "generado": "2026-09-30",
    },
    "epoch": EPOCH.strftime("%Y-%m-%d"),
    "dicts": {
        "pais": pais_cats,
        "tipo_viaje": tviaje_cats,
        "income": income_cats,
        "edad": edad_cats,
        "producto_main": prod_cats,
        "tipo_destino": tipo_dest_cats,
        "destino": dest_cats,
        "destino_tipo_idx": dest_tipo_idx,
        "tipo_origen": tipo_origen_cats,
        "origen": origen_cats,
        "origen_tipo_idx": origen_tipo_idx,
    },
    "rows": {
        "pais": pais_codes,
        "tipo_viaje": tviaje_codes,
        "income": income_codes,
        "edad": edad_codes,
        "producto": prod_codes,
        "destino": dest_codes,
        "origen": origen_codes,
        "confianza": conf_int,
        "dias_antic": dias_antic,
        "dias_timing": dias_timing,
        "fecha_day": fecha_day,
        "gb": gb,
    },
}

print("Serializando y guardando (puede tardar)...")
json_str = json.dumps(output, ensure_ascii=False, separators=(",", ":"), default=str)

with open(OUT_JS, "w", encoding="utf-8") as f:
    f.write("window.DASHBOARD_DATA = ")
    f.write(json_str)
    f.write(";")

size_mb = os.path.getsize(OUT_JS) / 1024 / 1024
print(f"  Guardado: {OUT_JS}")
print(f"  Tamaño: {size_mb:.1f} MB")
print("Listo.")

"""
KNN para recomendacion de segundo viaje.
Grupo B (2+ trips) entrena el modelo.
Grupo A (1 trip, todos del parquet) recibe la recomendacion.
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import NearestNeighbors

PARQUET = r"C:\xampp\htdocs\MKTBI\2nd_rebuy\Outputs\usuarios_features_knn.parquet"
OUTPUT  = r"C:\xampp\htdocs\MKTBI\2nd_rebuy\Outputs\recomendaciones_knn_v3.csv"

# ── 1. CARGAR ─────────────────────────────────────────────────────────────────
print("Cargando datos...")
df = pd.read_parquet(PARQUET)
print(f"  Parquet: {len(df):,} usuarios")

# ── 2. SEPARAR GRUPOS ─────────────────────────────────────────────────────────
grupo_b = df[df["tipo_usuario"] == "2 o mas trips"].copy()

# Grupo A = todos los usuarios con 1 trip del parquet (sin filtro externo)
grupo_a = df[df["tipo_usuario"] == "1 trip"].copy()

print(f"  Grupo B (referencia): {len(grupo_b):,}")
print(f"  Grupo A (target):     {len(grupo_a):,}")

# Grupo B necesita tener destino_trip_2 para ser util
grupo_b = grupo_b[grupo_b["destino_trip_2"].notna() & (grupo_b["destino_trip_2"] != "")]
print(f"  Grupo B con trip2 conocido: {len(grupo_b):,}")

# ── 3. FEATURES PARA MATCHING ─────────────────────────────────────────────────
ORDINALES = {
    "rango_edad_primer_trip": ["Sin dato", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
    "income":                 ["Unknown", "Low", "Medium", "High"],
    "bucket_anticipacion_compra": [
        "Sin dato", "0-6 dias", "7-29 dias", "30-89 dias", "90-179 dias", "180+ dias"
    ],
    "bucket_duracion_viaje": [
        "Sin dato", "1-3 dias", "4-7 dias", "8-14 dias", "15+ dias"
    ],
    "flight_class": ["Sin dato", "Sin vuelo", "ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"],
}

NOMINALES  = ["pais", "tipo_viaje", "product_type", "plataforma_trip_1", "tipo_destino"]
NUMERICAS  = ["log_gb_usd", "duracion_viaje_dias", "dias_anticipacion_compra_checkin"]
BINARIAS   = ["flg_uso_cupon", "flg_tarjeta_credito", "flg_puntos_loyalty_pago"]

def encodear(df_in, fit_cols=None):
    X = df_in[list(ORDINALES.keys()) + NOMINALES + NUMERICAS + BINARIAS].copy()

    # Ordinales → entero
    for col, cats in ORDINALES.items():
        enc = {c: i for i, c in enumerate(cats)}
        X[col] = X[col].fillna("Sin dato").astype(str).map(enc).fillna(0).astype(float)

    # Nominales → one-hot
    X = pd.get_dummies(X, columns=NOMINALES, dummy_na=False)

    # Numericas
    for col in NUMERICAS:
        X[col] = pd.to_numeric(X[col], errors="coerce").fillna(0)

    # Binarias
    for col in BINARIAS:
        X[col] = pd.to_numeric(X[col], errors="coerce").fillna(0)

    # Alinear columnas si se pasan columnas de referencia
    if fit_cols is not None:
        X = X.reindex(columns=fit_cols, fill_value=0)

    return X

print("\nEncoderando features...")
X_b = encodear(grupo_b)
X_a = encodear(grupo_a, fit_cols=X_b.columns)

print(f"  Features totales: {X_b.shape[1]}")

# ── 4. ESCALAR Y ENTRENAR KNN ─────────────────────────────────────────────────
print("Escalando y entrenando KNN...")
scaler   = StandardScaler()
X_b_sc   = scaler.fit_transform(X_b)
X_a_sc   = scaler.transform(X_a)

K = 5
knn = NearestNeighbors(n_neighbors=K, metric="euclidean", n_jobs=-1)
knn.fit(X_b_sc)

# ── 5. BUSCAR VECINOS ─────────────────────────────────────────────────────────
print(f"Buscando {K} vecinos para {len(grupo_a):,} usuarios...")
distances, indices = knn.kneighbors(X_a_sc)

# ── 6. RECOMENDACION ──────────────────────────────────────────────────────────
# Calcular dias entre checkout trip1 y compra trip2 para Grupo B
grupo_b["fecha_segundo_trip"] = pd.to_datetime(grupo_b["fecha_segundo_trip"], errors="coerce")
grupo_b["trip_checkout"]      = pd.to_datetime(grupo_b["trip_checkout"], errors="coerce")
grupo_b["dias_checkout_a_compra_2"] = (
    grupo_b["fecha_segundo_trip"] - grupo_b["trip_checkout"]
).dt.days

prod_b    = grupo_b["productos_trip_2"].values
dest_b    = grupo_b["destino_trip_2"].values
tipo_b    = grupo_b["tipo_destino_2"].values
antic_b   = grupo_b["dias_anticipacion_compra_2"].values
timing_b  = grupo_b["dias_checkout_a_compra_2"].values

def recomendar(vecinos_idx, vecinos_dist):
    pesos = 1.0 / (vecinos_dist + 1e-6)

    def moda_ponderada(valores):
        conteo = {}
        for v, w in zip(valores, pesos):
            if pd.notna(v) and v != "":
                conteo[v] = conteo.get(v, 0) + w
        return max(conteo, key=conteo.get) if conteo else None

    def promedio_ponderado(valores):
        vals  = [valores[i] for i in vecinos_idx]
        validos = [(v, w) for v, w in zip(vals, pesos) if pd.notna(v) and v >= 0]
        if not validos: return None
        total_w = sum(w for _, w in validos)
        return round(sum(v * w for v, w in validos) / total_w, 0)

    prod_rec  = moda_ponderada([prod_b[i] for i in vecinos_idx])
    dest_rec  = moda_ponderada([dest_b[i] for i in vecinos_idx])
    tipo_rec  = moda_ponderada([tipo_b[i] for i in vecinos_idx])
    antic_rec = promedio_ponderado(antic_b)   # dias anticipacion compra trip2
    timing_rec = promedio_ponderado(timing_b) # dias desde checkout trip1 a compra trip2

    # Confianza = % de vecinos que coinciden en producto
    prods = [prod_b[i] for i in vecinos_idx]
    conf  = round(sum(1 for p in prods if p == prod_rec) / len(prods), 2)

    return prod_rec, dest_rec, tipo_rec, conf, antic_rec, timing_rec

print("Generando recomendaciones...")
resultados = [recomendar(indices[i], distances[i]) for i in range(len(grupo_a))]

# ── 7. ARMAR OUTPUT ───────────────────────────────────────────────────────────
out = grupo_a[[
    "social_id", "pais", "tipo_viaje", "product_type",
    "tipo_destino", "destino_trip", "origen_trip", "rango_edad_primer_trip",
    "income", "gross_bookings_usd"
]].copy()

out["producto_recomendado"]          = [r[0] for r in resultados]
out["destino_recomendado"]           = [r[1] for r in resultados]
out["tipo_destino_recomendado"]      = [r[2] for r in resultados]
out["confianza"]                     = [r[3] for r in resultados]
out["dias_anticipacion_compra_2"]    = [r[4] for r in resultados]
out["dias_checkout_a_compra_2"]      = [r[5] for r in resultados]
out["distancia_vecino_1"]            = distances[:, 0].round(3)

# Fecha sugerida de comunicacion = checkout trip1 + dias_checkout_a_compra_2
grupo_a["trip_checkout"] = pd.to_datetime(grupo_a["trip_checkout"], errors="coerce")
out["trip_checkout"]     = grupo_a["trip_checkout"].values
out["fecha_comunicar"]   = pd.to_datetime(out["trip_checkout"]) + pd.to_timedelta(out["dias_checkout_a_compra_2"], unit="D")

# ── 8. GUARDAR ────────────────────────────────────────────────────────────────
out.to_csv(OUTPUT, index=False)
print(f"\nGuardado: {OUTPUT}")
print(f"Total recomendaciones: {len(out):,}")

# ── 9. RESUMEN ────────────────────────────────────────────────────────────────
print("\n=== Productos recomendados ===")
print(out["producto_recomendado"].value_counts(normalize=True).head(8).mul(100).round(1).to_string())

print("\n=== Tipo de destino recomendado ===")
print(out["tipo_destino_recomendado"].value_counts(normalize=True).head(10).mul(100).round(1).to_string())

print("\n=== Confianza promedio por producto ===")
print(out.groupby("producto_recomendado")["confianza"].mean().sort_values(ascending=False).head(8).round(2).to_string())

print("\n=== Ejemplos ===")
cols_show = ["social_id", "pais", "tipo_destino", "producto_recomendado", "destino_recomendado", "tipo_destino_recomendado", "confianza"]
print(out[cols_show].head(10).to_string(index=False))

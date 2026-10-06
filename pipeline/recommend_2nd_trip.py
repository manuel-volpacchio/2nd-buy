"""
Recomendacion de segundo viaje por matching KNN
------------------------------------------------
Grupo B (2+ trips): referencia - sabemos que compraron en trip2
Grupo A (1 trip):   target - buscamos al vecino mas parecido de B
                    y le recomendamos lo que ese vecino compro en trip2
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import OrdinalEncoder, StandardScaler
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import Pipeline
from collections import Counter

# ── 1. Carga ──────────────────────────────────────────────────────────────────
print("Cargando datos...")
df = pd.read_csv(
    r"C:\xampp\htdocs\MKTBI\2nd_rebuy\modeling_view_sample_100k.csv",
    low_memory=False
)
print(f"  Total: {len(df):,} filas")

# ── 2. Separar grupos ─────────────────────────────────────────────────────────
grupo_b = df[df["tipo_usuario"] == "2 o mas trips"].copy()
grupo_a = df[df["tipo_usuario"] == "1 trip"].copy()
print(f"  Grupo A (1 trip):    {len(grupo_a):,}")
print(f"  Grupo B (2+ trips):  {len(grupo_b):,}")

# Grupo B debe tener productos_trip_2 para ser util como referencia
grupo_b = grupo_b[grupo_b["productos_trip_2"].notna() & (grupo_b["productos_trip_2"] != "")]
print(f"  Grupo B con trip2 conocido: {len(grupo_b):,}")

# ── 3. Features para similitud ─────────────────────────────────────────────────
# Categoricas ordinales (con orden conocido)
ORDINALES = {
    "rango_edad_primer_trip": ["Sin dato", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
    "income":                 ["Unknown", "Low", "Medium", "High"],
    "bucket_anticipacion_compra": [
        "Sin dato", "0-6 dias", "7-29 dias", "30-89 dias",
        "90-179 dias", "180+ dias"
    ],
    "bucket_duracion_viaje": [
        "Sin dato", "1-3 dias", "4-7 dias", "8-14 dias", "15+ dias"
    ],
    "flight_class": ["Sin dato", "ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"],
}

# Categoricas nominales (one-hot)
NOMINALES = ["pais", "tipo_viaje", "product_type", "plataforma_trip_1"]

# Numericas
NUMERICAS = ["gross_bookings_usd", "duracion_viaje_dias", "dias_anticipacion_compra_checkin"]

# Binarias (ya son 0/1)
BINARIAS = ["tiene_vuelo", "flg_uso_cupon", "flg_tarjeta_credito", "flg_multi_plataforma_trip1"]

TODAS_LAS_FEATURES = list(ORDINALES.keys()) + NOMINALES + NUMERICAS + BINARIAS


def preparar_features(df_in):
    X = df_in[TODAS_LAS_FEATURES].copy()

    # Rellenar NaN en categoricas con "Sin dato"
    for col in list(ORDINALES.keys()) + NOMINALES:
        X[col] = X[col].fillna("Sin dato").astype(str)

    # Ordinales → entero
    for col, cats in ORDINALES.items():
        enc = {c: i for i, c in enumerate(cats)}
        X[col] = X[col].map(enc).fillna(0).astype(float)

    # Nominales → one-hot
    X = pd.get_dummies(X, columns=NOMINALES, dummy_na=False)

    # Numericas: rellenar con mediana y escalar
    for col in NUMERICAS:
        X[col] = pd.to_numeric(X[col], errors="coerce")
        mediana = X[col].median()
        X[col] = X[col].fillna(mediana)

    # Binarias: asegurar numerico
    for col in BINARIAS:
        X[col] = pd.to_numeric(X[col], errors="coerce").fillna(0)

    return X


# ── 4. Alinear columnas A y B (one-hot puede diferir) ────────────────────────
print("\nPreparando features...")
X_b_raw = preparar_features(grupo_b)
X_a_raw = preparar_features(grupo_a)

# Unir columnas (llenar con 0 las que falten en alguno)
all_cols = sorted(set(X_b_raw.columns) | set(X_a_raw.columns))
X_b = X_b_raw.reindex(columns=all_cols, fill_value=0)
X_a = X_a_raw.reindex(columns=all_cols, fill_value=0)

print(f"  Features totales: {len(all_cols)}")

# ── 5. Escalar y ajustar KNN sobre Grupo B ────────────────────────────────────
print("Entrenando KNN...")
scaler = StandardScaler()
X_b_scaled = scaler.fit_transform(X_b)
X_a_scaled = scaler.transform(X_a)

K = 5
knn = NearestNeighbors(n_neighbors=K, metric="euclidean", n_jobs=-1)
knn.fit(X_b_scaled)

# ── 6. Para cada usuario de A, encontrar los K vecinos en B ──────────────────
print(f"Buscando {K} vecinos más cercanos para {len(grupo_a):,} usuarios de Grupo A...")
distances, indices = knn.kneighbors(X_a_scaled)

# ── 7. Recomendacion = producto_trip_2 mas frecuente entre vecinos ────────────
productos_b = grupo_b["productos_trip_2"].values

def recomendar(vecino_indices, vecino_distancias):
    prods = [productos_b[i] for i in vecino_indices]
    # Moda ponderada por 1/distancia (distancia 0 → peso infinito, usar epsilon)
    pesos = 1.0 / (vecino_distancias + 1e-6)
    conteo = {}
    for p, w in zip(prods, pesos):
        conteo[p] = conteo.get(p, 0) + w
    return max(conteo, key=conteo.get)

recomendaciones = [
    recomendar(indices[i], distances[i])
    for i in range(len(grupo_a))
]

# ── 8. Armar output ───────────────────────────────────────────────────────────
resultado = grupo_a[["social_id", "pais", "tipo_viaje", "product_type",
                      "destino_trip", "rango_edad_primer_trip", "income",
                      "gross_bookings_usd"]].copy()
resultado["producto_recomendado_trip2"] = recomendaciones
resultado["distancia_vecino_mas_cercano"] = distances[:, 0].round(3)

# Calcular confianza: % de vecinos que coinciden en la recomendacion
def confianza(vecino_indices, rec):
    prods = [productos_b[i] for i in vecino_indices]
    return round(sum(1 for p in prods if p == rec) / len(prods), 2)

resultado["confianza"] = [
    confianza(indices[i], recomendaciones[i])
    for i in range(len(grupo_a))
]

# ── 9. Guardar ────────────────────────────────────────────────────────────────
out_path = r"C:\xampp\htdocs\MKTBI\2nd_rebuy\Outputs\recomendaciones_2do_viaje.csv"
resultado.to_csv(out_path, index=False)
print(f"\nGuardado: {out_path}")
print(f"Total recomendaciones: {len(resultado):,}")

# ── 10. Resumen rapido ────────────────────────────────────────────────────────
print("\n=== Distribucion de recomendaciones ===")
dist = resultado["producto_recomendado_trip2"].value_counts(normalize=True).head(10)
for prod, pct in dist.items():
    print(f"  {prod:<40} {pct*100:.1f}%")

print("\n=== Confianza promedio por producto recomendado ===")
conf_avg = resultado.groupby("producto_recomendado_trip2")["confianza"].mean().sort_values(ascending=False)
print(conf_avg.head(10).to_string())

print("\n=== Ejemplo de recomendaciones ===")
print(resultado[["social_id", "pais", "product_type", "destino_trip",
                  "producto_recomendado_trip2", "confianza"]].head(10).to_string(index=False))

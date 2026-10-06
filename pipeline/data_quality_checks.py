"""
Checks previos al KNN:
1. Regionalizar destino_trip
2. Missings en features clave
3. Distribucion de gross_bookings_usd
4. Cardinalidad de destino_trip_2
"""

import pandas as pd
import numpy as np

PATH = r"C:\xampp\htdocs\MKTBI\2nd_rebuy\Outputs\usuarios_2022_plus.parquet"
print("Cargando parquet...")
df = pd.read_csv(PATH) if PATH.endswith(".csv") else pd.read_parquet(PATH)
print(f"  {len(df):,} filas  |  {df['tipo_usuario'].value_counts().to_dict()}")

grupo_a = df[df["tipo_usuario"] == "1 trip"]
grupo_b = df[df["tipo_usuario"] == "2 o mas trips"]

# ── 1. MISSINGS EN FEATURES CLAVE ────────────────────────────────────────────
print("\n=== 1. MISSINGS EN FEATURES CLAVE ===")
features = [
    "pais", "tipo_viaje", "product_type", "destino_trip", "origen_trip",
    "plataforma_trip_1", "flight_class", "rango_edad_primer_trip", "income",
    "bucket_anticipacion_compra", "bucket_duracion_viaje",
    "gross_bookings_usd", "flg_uso_cupon", "flg_tarjeta_credito",
]
for col in features:
    if col not in df.columns:
        print(f"  {col:<35} COLUMNA NO EXISTE")
        continue
    null_a = grupo_a[col].isna().mean() * 100
    null_b = grupo_b[col].isna().mean() * 100
    print(f"  {col:<35} A: {null_a:5.1f}%  B: {null_b:5.1f}%")

# ── 2. DISTRIBUCION gross_bookings_usd ────────────────────────────────────────
print("\n=== 2. DISTRIBUCION gross_bookings_usd ===")
gb = df["gross_bookings_usd"].dropna()
print(f"  Min:    {gb.min():>12,.2f}")
print(f"  p1:     {gb.quantile(0.01):>12,.2f}")
print(f"  p25:    {gb.quantile(0.25):>12,.2f}")
print(f"  p50:    {gb.quantile(0.50):>12,.2f}")
print(f"  p75:    {gb.quantile(0.75):>12,.2f}")
print(f"  p95:    {gb.quantile(0.95):>12,.2f}")
print(f"  p99:    {gb.quantile(0.99):>12,.2f}")
print(f"  Max:    {gb.max():>12,.2f}")
print(f"  Ceros:  {(gb == 0).sum():>12,}  ({(gb==0).mean()*100:.1f}%)")
print(f"  Negativos: {(gb < 0).sum():>9,}  ({(gb<0).mean()*100:.1f}%)")
print(f"  > 10k:  {(gb > 10000).sum():>12,}  ({(gb>10000).mean()*100:.1f}%)")

# ── 3. CARDINALIDAD destino_trip y destino_trip_2 ────────────────────────────
print("\n=== 3. CARDINALIDAD DESTINOS ===")
for col in ["destino_trip", "destino_trip_2"]:
    if col not in df.columns:
        print(f"  {col}: COLUMNA NO EXISTE")
        continue
    src = grupo_b[col] if col == "destino_trip_2" else df[col]
    n_unique = src.nunique()
    top5 = src.value_counts().head(5)
    top5_pct = top5 / src.notna().sum() * 100
    print(f"\n  {col} — {n_unique:,} valores únicos")
    for dest, pct in top5_pct.items():
        print(f"    {dest:<8} {pct:.1f}%")

# ── 4. REGIONALIZACION ───────────────────────────────────────────────────────
print("\n=== 4. REGIONALIZACION destino_trip ===")

REGIONES = {
    # Brasil
    "SAO": "BR_SAO", "GRU": "BR_SAO", "CGH": "BR_SAO",
    "RIO": "BR_RIO", "GIG": "BR_RIO", "SDU": "BR_RIO",
    "REC": "BR_NE",  "FOR": "BR_NE",  "SSA": "BR_NE",  "MCZ": "BR_NE",
    "NAT": "BR_NE",  "JPA": "BR_NE",  "THE": "BR_NE",
    "BEL": "BR_N",   "MAN": "BR_N",
    "BSB": "BR_CO",  "CGR": "BR_CO",  "CGB": "BR_CO",
    "POA": "BR_S",   "FLN": "BR_S",   "CWB": "BR_S",   "IGU": "BR_S",
    "BHZ": "BR_SE",  "VIX": "BR_SE",  "GYN": "BR_CO",
    # Argentina
    "BUE": "AR_BUE", "AEP": "AR_BUE", "EZE": "AR_BUE",
    "COR": "AR_INT", "MDZ": "AR_INT", "ROS": "AR_INT",
    "NQN": "AR_PAT", "BRC": "AR_PAT", "USH": "AR_PAT",
    "IGR": "AR_INT", "SLA": "AR_INT",
    # Chile
    "SCL": "CL_SCL",
    "PMC": "CL_SUR", "ZCO": "CL_SUR", "PUQ": "CL_SUR",
    "IQQ": "CL_NOR", "ANF": "CL_NOR", "CJC": "CL_NOR",
    # Mexico
    "MEX": "MX_MEX", "CUN": "CAR_MX", "SJD": "MX_PAC",
    "GDL": "MX_INT", "MTY": "MX_INT", "CUU": "MX_INT",
    "MZT": "MX_PAC", "PVR": "MX_PAC", "ZIH": "MX_PAC",
    # Caribe
    "PUJ": "CAR_DO", "SDQ": "CAR_DO",
    "HAV": "CAR_CU", "VRA": "CAR_CU",
    "NAS": "CAR_BS", "MBJ": "CAR_JM",
    "SJU": "CAR_PR", "STT": "CAR_VI",
    # Colombia
    "BOG": "CO_BOG", "MDE": "CO_INT", "CTG": "CO_INT", "CLO": "CO_INT",
    # Peru / Ecuador / Bolivia
    "LIM": "PER",    "GYE": "ECU",    "UIO": "ECU",    "LPB": "BOL",
    # Uruguay / Paraguay
    "MVD": "UY",     "ASU": "PY",
    # Europa
    "MAD": "EU_IB",  "BCN": "EU_IB",  "LIS": "EU_IB",
    "GRU_EU": "EU",  "CDG": "EU",     "LHR": "EU",     "FCO": "EU",
    "AMS": "EU",     "FRA": "EU",     "MXP": "EU",
    # USA
    "MIA": "USA",    "NYC": "USA",    "JFK": "USA",    "LAX": "USA",
    "MCO": "USA",    "EWR": "USA",
    # Resto
    "CZM": "CAR_MX",
}

df["region_destino"] = df["destino_trip"].map(REGIONES).fillna("OTRO")
cobertura = df["region_destino"].ne("OTRO").mean() * 100
print(f"  Cobertura del mapeo: {cobertura:.1f}%")
print(f"  Distribución top regiones:")
print(df["region_destino"].value_counts().head(12).to_string())

# Cuántos destinos únicos caen en OTRO
otros = df[df["region_destino"] == "OTRO"]["destino_trip"].value_counts().head(20)
print(f"\n  Top destinos sin mapear (para completar el diccionario):")
print(otros.head(20).to_string())

"""
Prepara el dataset para KNN:
1. Imputa missings
2. Log-transform gross_bookings_usd
3. Regionaliza destinos (trip1 y trip2)
4. Guarda parquet listo para KNN
"""

import pandas as pd
import numpy as np
from pathlib import Path

INPUT  = Path(r"C:\xampp\htdocs\MKTBI\2nd_rebuy\Outputs\usuarios_2022_plus.parquet")
OUTPUT = Path(r"C:\xampp\htdocs\MKTBI\2nd_rebuy\Outputs\usuarios_features_knn.parquet")

print("Cargando...")
df = pd.read_parquet(INPUT)
print(f"  {len(df):,} usuarios")

# ── 1. IMPUTAR MISSINGS ───────────────────────────────────────────────────────
df["origen_trip"]   = df["origen_trip"].fillna("Sin vuelo")
df["flight_class"]  = df["flight_class"].fillna("Sin vuelo")
df["income"]        = df["income"].fillna("Unknown")

# ── 2. LOG-TRANSFORM gross_bookings_usd ───────────────────────────────────────
# Negativos y ceros → 0 antes del log
df["gross_bookings_usd"] = df["gross_bookings_usd"].clip(lower=0)
df["log_gb_usd"] = np.log1p(df["gross_bookings_usd"])

# ── 3. REGIONALIZACION ───────────────────────────────────────────────────────
REGIONES = {
    # ── Brasil São Paulo ──────────────────────────────────────────────────────
    "SAO": "BR_SAO", "GRU": "BR_SAO", "CGH": "BR_SAO", "VCP": "BR_SAO",
    # ── Brasil Río de Janeiro ─────────────────────────────────────────────────
    "RIO": "BR_RIO", "GIG": "BR_RIO", "SDU": "BR_RIO",
    # ── Brasil Nordeste ───────────────────────────────────────────────────────
    "REC": "BR_NE", "FOR": "BR_NE", "SSA": "BR_NE", "MCZ": "BR_NE",
    "NAT": "BR_NE", "JPA": "BR_NE", "THE": "BR_NE", "BPS": "BR_NE",
    "AJU": "BR_NE", "SLZ": "BR_NE", "JDO": "BR_NE", "IOS": "BR_NE",
    "PMW": "BR_NE", "STM": "BR_NE", "IMP": "BR_NE", "BEL": "BR_NE",
    # ── Brasil Norte ─────────────────────────────────────────────────────────
    "MAN": "BR_N",  "MAO": "BR_N",  "PVH": "BR_N",  "BOA": "BR_N",
    "TBT": "BR_N",
    # ── Brasil Centro-Oeste ───────────────────────────────────────────────────
    "BSB": "BR_CO", "CGR": "BR_CO", "CGB": "BR_CO", "GYN": "BR_CO",
    # ── Brasil Sur ───────────────────────────────────────────────────────────
    "POA": "BR_S",  "FLN": "BR_S",  "CWB": "BR_S",  "IGU": "BR_S",
    "NVT": "BR_S",  "XAP": "BR_S",  "LDB": "BR_S",
    # ── Brasil Sudeste (no SP/RIO) ────────────────────────────────────────────
    "BHZ": "BR_SE", "VIX": "BR_SE", "UDI": "BR_SE", "IPN": "BR_SE",
    "ORL": "BR_SE", "PLU": "BR_SE",
    # ── Argentina Buenos Aires ────────────────────────────────────────────────
    "BUE": "AR_BUE", "AEP": "AR_BUE", "EZE": "AR_BUE",
    # ── Argentina Interior ────────────────────────────────────────────────────
    "COR": "AR_INT", "MDZ": "AR_INT", "ROS": "AR_INT", "TUC": "AR_INT",
    "SLA": "AR_INT", "IGR": "AR_INT", "JUJ": "AR_INT", "CNQ": "AR_INT",
    "RES": "AR_INT", "SFN": "AR_INT", "MDP": "AR_INT", "BHI": "AR_INT",
    "LUQ": "AR_INT",
    # ── Argentina Patagonia ───────────────────────────────────────────────────
    "NQN": "AR_PAT", "BRC": "AR_PAT", "USH": "AR_PAT", "PMY": "AR_PAT",
    "REL": "AR_PAT", "VDM": "AR_PAT", "RGA": "AR_PAT",
    # ── Chile Santiago ────────────────────────────────────────────────────────
    "SCL": "CL_SCL",
    # ── Chile Sur ────────────────────────────────────────────────────────────
    "PMC": "CL_SUR", "ZCO": "CL_SUR", "PUQ": "CL_SUR", "MHC": "CL_SUR",
    "WPU": "CL_SUR",
    # ── Chile Norte ───────────────────────────────────────────────────────────
    "IQQ": "CL_NOR", "ANF": "CL_NOR", "CJC": "CL_NOR", "ARI": "CL_NOR",
    # ── Mexico Ciudad de Mexico ───────────────────────────────────────────────
    "MEX": "MX_MEX",
    # ── Mexico Pacifico ───────────────────────────────────────────────────────
    "SJD": "MX_PAC", "MZT": "MX_PAC", "PVR": "MX_PAC", "ZIH": "MX_PAC",
    "MXL": "MX_PAC", "HMO": "MX_PAC", "LMM": "MX_PAC", "ACA": "MX_PAC",
    # ── Mexico Interior ───────────────────────────────────────────────────────
    "GDL": "MX_INT", "MTY": "MX_INT", "CUU": "MX_INT", "AGU": "MX_INT",
    "SLP": "MX_INT", "BJX": "MX_INT", "OAX": "MX_INT", "VSA": "MX_INT",
    "MLM": "MX_INT", "CME": "MX_INT",
    # ── Mexico Caribe ─────────────────────────────────────────────────────────
    "CUN": "CAR_MX", "CZM": "CAR_MX",
    # ── Caribe República Dominicana ───────────────────────────────────────────
    "PUJ": "CAR_DO", "SDQ": "CAR_DO", "STI": "CAR_DO",
    # ── Caribe Cuba ───────────────────────────────────────────────────────────
    "HAV": "CAR_CU", "VRA": "CAR_CU", "HOG": "CAR_CU",
    # ── Caribe otros ──────────────────────────────────────────────────────────
    "NAS": "CAR_OT", "MBJ": "CAR_OT", "SJU": "CAR_OT", "STT": "CAR_OT",
    "BGI": "CAR_OT", "GCM": "CAR_OT", "ANU": "CAR_OT",
    # ── Colombia Bogotá ───────────────────────────────────────────────────────
    "BOG": "CO_BOG",
    # ── Colombia Interior ─────────────────────────────────────────────────────
    "MDE": "CO_INT", "CTG": "CO_INT", "CLO": "CO_INT", "BAQ": "CO_INT",
    "SMR": "CO_INT", "ADZ": "CO_INT", "CUC": "CO_INT", "MTR": "CO_INT",
    "PEI": "CO_INT", "BGA": "CO_INT", "EJA": "CO_INT", "IBE": "CO_INT",
    "LET": "CO_INT", "VVC": "CO_INT", "AXM": "CO_INT",
    # ── Peru ─────────────────────────────────────────────────────────────────
    "LIM": "PER", "CUZ": "PER", "AQP": "PER", "IQT": "PER",
    # ── Ecuador ───────────────────────────────────────────────────────────────
    "GYE": "ECU", "UIO": "ECU", "GPS": "ECU",
    # ── Bolivia ───────────────────────────────────────────────────────────────
    "LPB": "BOL", "VVI": "BOL", "CBB": "BOL",
    # ── Uruguay ───────────────────────────────────────────────────────────────
    "MVD": "UY", "PDP": "UY",
    # ── Paraguay ──────────────────────────────────────────────────────────────
    "ASU": "PY",
    # ── Venezuela ────────────────────────────────────────────────────────────
    "CCS": "VE", "MAR": "VE",
    # ── Europa Iberica ────────────────────────────────────────────────────────
    "MAD": "EU_IB", "BCN": "EU_IB", "LIS": "EU_IB", "OPO": "EU_IB",
    "SVQ": "EU_IB", "AGP": "EU_IB", "ALC": "EU_IB",
    # ── Europa Resto ─────────────────────────────────────────────────────────
    "CDG": "EU_OT", "LHR": "EU_OT", "FCO": "EU_OT", "AMS": "EU_OT",
    "FRA": "EU_OT", "MXP": "EU_OT", "MUC": "EU_OT", "ZRH": "EU_OT",
    "VIE": "EU_OT", "BRU": "EU_OT", "ARN": "EU_OT", "CPH": "EU_OT",
    "DUB": "EU_OT", "PRG": "EU_OT", "BUD": "EU_OT", "WAW": "EU_OT",
    "IST": "EU_OT", "ATH": "EU_OT", "HEL": "EU_OT",
    # ── USA / Canada ──────────────────────────────────────────────────────────
    "MIA": "USA",   "JFK": "USA",   "LAX": "USA",   "MCO": "USA",
    "EWR": "USA",   "ORD": "USA",   "ATL": "USA",   "SFO": "USA",
    "YYZ": "USA",   "YUL": "USA",
    # ── Asia / Oceania ────────────────────────────────────────────────────────
    "NRT": "ASIA",  "HND": "ASIA",  "ICN": "ASIA",  "BKK": "ASIA",
    "SIN": "ASIA",  "DXB": "ASIA",  "SYD": "ASIA",  "AKL": "ASIA",
    "PEK": "ASIA",  "PVG": "ASIA",
}

for col_in, col_out in [("destino_trip", "region_destino"), ("destino_trip_2", "region_destino_2")]:
    if col_in in df.columns:
        df[col_out] = df[col_in].map(REGIONES).fillna("OTRO")
        cob = df[col_out].ne("OTRO").mean() * 100
        print(f"  {col_out}: cobertura {cob:.1f}%")

# ── 4. RESUMEN FINAL ─────────────────────────────────────────────────────────
print("\n=== Dataset listo ===")
print(f"  Filas: {len(df):,}")
print(f"  Columnas: {len(df.columns)}")

print("\n  Missings post-fix en features clave:")
for col in ["origen_trip", "flight_class", "income", "log_gb_usd", "region_destino"]:
    null_pct = df[col].isna().mean() * 100
    print(f"    {col:<30} {null_pct:.1f}%")

print("\n  Top regiones destino trip1:")
print(df["region_destino"].value_counts().head(10).to_string())

print("\n  Top regiones destino trip2 (Grupo B):")
grupo_b = df[df["tipo_usuario"] == "2 o mas trips"]
print(grupo_b["region_destino_2"].value_counts().head(10).to_string())

# ── 5. GUARDAR ────────────────────────────────────────────────────────────────
df.to_parquet(OUTPUT, index=False)
mb = OUTPUT.stat().st_size / 1024 / 1024
print(f"\nGuardado: {OUTPUT}  ({mb:.0f} MB)")

"""
Clasificacion manual de destinos por tipo de viaje.
Cubre el 81%+ del volumen con los top 80 destinos.
El resto queda como OTRO (se puede expandir).
"""

import pandas as pd
import numpy as np
from pathlib import Path

INPUT  = Path(r"C:\xampp\htdocs\MKTBI\2nd_rebuy\Outputs\usuarios_features_knn.parquet")
OUTPUT = Path(r"C:\xampp\htdocs\MKTBI\2nd_rebuy\Outputs\usuarios_features_knn.parquet")

TIPO_DESTINO = {

    # ── PLAYA CARIBE ─────────────────────────────────────────────────────────
    # Resorts de sol y playa, vuelos directos, todo incluido
    "CUN": "PLAYA_CARIBE",  "CZM": "PLAYA_CARIBE",
    "PUJ": "PLAYA_CARIBE",  "SDQ": "PLAYA_CARIBE",  "STI": "PLAYA_CARIBE",
    "HAV": "PLAYA_CARIBE",  "VRA": "PLAYA_CARIBE",  "HOG": "PLAYA_CARIBE",
    "ADZ": "PLAYA_CARIBE",  "SMR": "PLAYA_CARIBE",  "CTG": "PLAYA_CARIBE",
    "NAS": "PLAYA_CARIBE",  "MBJ": "PLAYA_CARIBE",  "SJU": "PLAYA_CARIBE",
    "CAY": "PLAYA_CARIBE",

    # ── PLAYA BRASIL ──────────────────────────────────────────────────────────
    # Playa nacional brasileña — perfil diferente al Caribe (más corto, más económico)
    "REC": "PLAYA_BR",  "FOR": "PLAYA_BR",  "SSA": "PLAYA_BR",
    "MCZ": "PLAYA_BR",  "NAT": "PLAYA_BR",  "JPA": "PLAYA_BR",
    "BPS": "PLAYA_BR",  "AJU": "PLAYA_BR",  "IOS": "PLAYA_BR",
    "JDO": "PLAYA_BR",  "PNZ": "PLAYA_BR",  "THE": "PLAYA_BR",
    "SLZ": "PLAYA_BR",  "FLN": "PLAYA_BR",  "NVT": "PLAYA_BR",
    "IGU": "PLAYA_BR",

    # ── PLAYA MEXICO PACIFICO ─────────────────────────────────────────────────
    "PVR": "PLAYA_MX",  "SJD": "PLAYA_MX",  "MZT": "PLAYA_MX",
    "ACA": "PLAYA_MX",  "ZIH": "PLAYA_MX",

    # ── CIUDAD HUB ────────────────────────────────────────────────────────────
    # Grandes ciudades de conexión / negocios / turismo urbano masivo
    "SAO": "CIUDAD_HUB",  "GRU": "CIUDAD_HUB",  "CGH": "CIUDAD_HUB",
    "BUE": "CIUDAD_HUB",  "AEP": "CIUDAD_HUB",  "EZE": "CIUDAD_HUB",
    "BOG": "CIUDAD_HUB",  "SCL": "CIUDAD_HUB",
    "MEX": "CIUDAD_HUB",  "LIM": "CIUDAD_HUB",
    "BSB": "CIUDAD_HUB",  "GYN": "CIUDAD_HUB",

    # ── CIUDAD TURISTICA ──────────────────────────────────────────────────────
    # Ciudad con fuerte atractivo turístico, no necesariamente hub
    "RIO": "CIUDAD_TUR",  "BHZ": "CIUDAD_TUR",  "CWB": "CIUDAD_TUR",
    "POA": "CIUDAD_TUR",  "BEL": "CIUDAD_TUR",  "MAO": "CIUDAD_TUR",
    "ORL": "CIUDAD_TUR",  "VIX": "CIUDAD_TUR",  "CGR": "CIUDAD_TUR",
    "CGB": "CIUDAD_TUR",  "MDE": "CIUDAD_TUR",  "CLO": "CIUDAD_TUR",
    "BAQ": "CIUDAD_TUR",  "CUC": "CIUDAD_TUR",  "MTR": "CIUDAD_TUR",
    "PEI": "CIUDAD_TUR",  "BGA": "CIUDAD_TUR",  "PTY": "CIUDAD_TUR",
    "CCS": "CIUDAD_TUR",

    # ── CIUDAD INTERIOR ARGENTINA ─────────────────────────────────────────────
    "COR": "CIUDAD_AR",  "MDZ": "CIUDAD_AR",  "ROS": "CIUDAD_AR",
    "TUC": "CIUDAD_AR",  "SLA": "CIUDAD_AR",  "JUJ": "CIUDAD_AR",
    "NQN": "CIUDAD_AR",  "MDQ": "CIUDAD_AR",

    # ── MONTANA / AVENTURA / NATURALEZA ───────────────────────────────────────
    # Destinos de nieve, trekking, naturaleza — perfil activo, duración media
    "BRC": "MONTANA_NAT",  "USH": "MONTANA_NAT",
    "PMC": "MONTANA_NAT",  "ZCO": "MONTANA_NAT",  "PUQ": "MONTANA_NAT",
    "CJC": "MONTANA_NAT",  "IQQ": "MONTANA_NAT",  "ANF": "MONTANA_NAT",
    "LSC": "MONTANA_NAT",
    "CUZ": "MONTANA_NAT",  "AQP": "MONTANA_NAT",
    "FTE": "MONTANA_NAT",

    # ── CATARATAS / NATURALEZA PUNTUAL ────────────────────────────────────────
    "IGR": "CATARATAS",   # Iguazú lado argentino
    "IGU": "CATARATAS",   # Iguazú lado brasileño

    # ── MEXICO INTERIOR ───────────────────────────────────────────────────────
    "GDL": "MX_INT",  "MTY": "MX_INT",  "MID": "MX_INT",
    "TIJ": "MX_INT",  "CUU": "MX_INT",

    # ── COLOMBIA BOGOTA ───────────────────────────────────────────────────────
    # ya está en CIUDAD_HUB

    # ── EUROPA ────────────────────────────────────────────────────────────────
    "MAD": "EUROPA",  "BCN": "EUROPA",  "LIS": "EUROPA",
    "CDG": "EUROPA",  "FCO": "EUROPA",  "AMS": "EUROPA",
    "FRA": "EUROPA",  "MXP": "EUROPA",  "LHR": "EUROPA",
    "ROM": "EUROPA",  "PAR": "EUROPA",  "LON": "EUROPA",
    "ZRH": "EUROPA",  "VIE": "EUROPA",  "IST": "EUROPA",
    "OPO": "EUROPA",  "SVQ": "EUROPA",  "AGP": "EUROPA",
    "MIL": "EUROPA",  "VER": "EUROPA",  "VCE": "EUROPA",
    "CHI": "EUROPA",  "BRU": "EUROPA",  "PRG": "EUROPA",
    "BUD": "EUROPA",  "WAW": "EUROPA",  "ATH": "EUROPA",
    "CPH": "EUROPA",  "ARN": "EUROPA",  "HEL": "EUROPA",
    "DUB": "EUROPA",  "EDI": "EUROPA",  "MAN": "EUROPA",

    # ── USA / CANADA ──────────────────────────────────────────────────────────
    "NYC": "USA_CA",  "MIA": "USA_CA",  "LAX": "USA_CA",
    "MCO": "USA_CA",  "LAS": "USA_CA",  "JFK": "USA_CA",
    "EWR": "USA_CA",  "ORD": "USA_CA",  "SFO": "USA_CA",
    "YYZ": "USA_CA",

    # ── URUGUAY / PARAGUAY ────────────────────────────────────────────────────
    "MVD": "CIUDAD_TUR",  "PDP": "PLAYA_BR",
    "ASU": "CIUDAD_TUR",

    # ── ASIA / OCEANIA ────────────────────────────────────────────────────────
    "TYO": "ASIA",  "NRT": "ASIA",  "HND": "ASIA",
    "ICN": "ASIA",  "BKK": "ASIA",  "SIN": "ASIA",
    "DXB": "ASIA",  "SYD": "ASIA",  "AKL": "ASIA",

    # ── USA ADICIONALES ───────────────────────────────────────────────────────
    "FLL": "USA_CA",  "YTO": "USA_CA",  "WAS": "USA_CA",
    "DFW": "USA_CA",  "SEA": "USA_CA",  "BOS": "USA_CA",
    "YVR": "USA_CA",  "YUL": "USA_CA",  "CHI": "USA_CA",

    # ── MONTANA ADICIONALES ───────────────────────────────────────────────────
    "CPC": "MONTANA_NAT",   # San Martín de los Andes
    "CHE": "MONTANA_NAT",   # Chapelco

    # ── CIUDAD_TUR ADICIONALES ────────────────────────────────────────────────
    "UIO": "CIUDAD_TUR",  "GYE": "CIUDAD_TUR",
    "UDI": "CIUDAD_TUR",  "RAO": "CIUDAD_TUR",
    "MGF": "CIUDAD_TUR",  "SJP": "CIUDAD_TUR",
    "JOI": "CIUDAD_TUR",  "CLV": "CIUDAD_TUR",
    "BZC": "PLAYA_BR",

    # ── CIUDAD_AR ADICIONALES ─────────────────────────────────────────────────
    "PSS": "CIUDAD_AR",   # Posadas
    "CCP": "CIUDAD_AR",   # Concepción (Chile, perfil similar)
    "RES": "CIUDAD_AR",   "CNQ": "CIUDAD_AR",
    "BHI": "CIUDAD_AR",   "SFN": "CIUDAD_AR",

    # ── PLAYA BR ADICIONALES ──────────────────────────────────────────────────
    "XAP": "PLAYA_BR",   # Chapecó tiene perfil diferente pero lo dejamos BR
    "JJD": "PLAYA_BR",   # Jijoca/Jericoacoara
    "HUX": "PLAYA_MX",   # Huatulco
    "PXM": "PLAYA_MX",   # Puerto Escondido

    # ── CIUDAD_TUR ADICIONALES ────────────────────────────────────────────────
    "LDB": "CIUDAD_TUR",  # Londrina (BR)
    "CPV": "CIUDAD_TUR",  # Campina Grande (BR)
    "PIU": "CIUDAD_TUR",  # Piura (PE)
    "TPP": "CIUDAD_TUR",  # Tarapoto (PE)
    "MCP": "CIUDAD_TUR",  # Macapá (BR)
    "FEN": "CIUDAD_TUR",  # Fernando de Noronha (BR)
    "STM": "CIUDAD_TUR",  # Santarém (BR)
    "PSO": "CIUDAD_TUR",  # Pasto (CO)
    "ARI": "CIUDAD_TUR",  # Arica (CL)
    "CRD": "CIUDAD_AR",   # Comodoro Rivadavia
    "VER": "CIUDAD_TUR",  # Veracruz (MX) si no es Europa

    # ── BRASIL RESTO (no playa, no hub) ──────────────────────────────────────
    "GR3": "BR_OTRO",   # codigo interno Despegar
    "PMW": "BR_OTRO",   "VDC": "BR_OTRO",
    "QJO": "BR_OTRO",   "BBCAM": "BR_OTRO",
}

def _main():
    print("Cargando parquet...")
    df = pd.read_parquet(INPUT)
    print(f"  {len(df):,} usuarios")

    for col_in, col_out in [("destino_trip", "tipo_destino"), ("destino_trip_2", "tipo_destino_2")]:
        if col_in not in df.columns:
            continue
        df[col_out] = df[col_in].map(TIPO_DESTINO).fillna("OTRO")
        n_total = df[col_in].notna().sum()
        n_mapeado = df[col_out].ne("OTRO").sum()
        print(f"\n  {col_out}: {n_mapeado/n_total*100:.1f}% cobertura ({n_mapeado:,} / {n_total:,})")

        print(f"  Distribución:")
        dist = df[col_out].value_counts()
        for tipo, cnt in dist.items():
            print(f"    {tipo:<20} {cnt:>9,}  ({cnt/n_total*100:.1f}%)")

    # Destinos sin mapear más frecuentes
    print("\n=== Destinos trip1 sin mapear (top 20) ===")
    sin_mapeo = df[df["tipo_destino"] == "OTRO"]["destino_trip"].value_counts().head(20)
    for dest, cnt in sin_mapeo.items():
        print(f"  {dest:<8} {cnt:>8,}")

    df.to_parquet(OUTPUT, index=False)
    print(f"\nGuardado: {OUTPUT}")


# Solo se ejecuta si se corre el script directamente (python clasificar_destinos.py).
# Al importarlo desde otro script (ej. build_dashboard_data.py para usar TIPO_DESTINO)
# no debe reescribir el parquet.
if __name__ == "__main__":
    _main()

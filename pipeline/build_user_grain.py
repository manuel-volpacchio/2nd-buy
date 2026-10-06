"""
Consolida los archivos historicos mensuales en un dataset a grano usuario.
- Filtra nro_trip = 1 (los trip2 vienen como columnas denormalizadas)
- Agrega a un registro por social_id
- Guarda como Parquet (~300MB vs 11GB original)
"""

import pandas as pd
import numpy as np
from pathlib import Path

HISTORICO = Path(r"C:\xampp\htdocs\MKTBI\2nd_rebuy\historico")
OUTPUT    = Path(r"C:\xampp\htdocs\MKTBI\2nd_rebuy\Outputs\usuarios_2022_plus.parquet")

# Columnas que necesitamos (trip1 features + trip2 targets)
COLS = [
    # Identidad
    "social_id", "tipo_usuario",
    # Contexto temporal
    "fecha_primer_trip", "fecha_segundo_trip",
    # Features trip 1 (para matching)
    "pais", "tipo_viaje", "product_type", "purchase_type",
    "destino_trip", "origen_trip",
    "plataforma_trip_1", "canales_compra_trip_1",
    "flight_class", "tiene_vuelo",
    "rango_edad_primer_trip", "income",
    "bucket_anticipacion_compra", "bucket_duracion_viaje",
    "duracion_viaje_dias", "dias_anticipacion_compra_checkin",
    "gross_bookings_usd",
    "flg_uso_cupon", "flg_tarjeta_credito", "flg_transferencia",
    "flg_puntos_loyalty_pago",
    "productos_trip_1",
    # Targets trip 2 (lo que queremos recomendar)
    "destino_trip_2", "origen_trip_2",
    "tipo_viaje_2", "productos_trip_2",
    "trip_checkin", "trip_checkout",
    "duracion_viaje_dias_2", "dias_anticipacion_compra_2",
    "gross_bookings_usd_2", "flg_uso_cupon_2", "flight_class_2",
    "plataforma_trip_2", "canales_compra_trip_2",
    "flg_mismo_producto_trip_1_2",
]

archivos = sorted(HISTORICO.glob("rebuy_final_202[2-9]_*.csv"))

print(f"Archivos a procesar: {len(archivos)}")
total_rows_raw = 0
partes = []

for i, archivo in enumerate(archivos):
    print(f"  [{i+1:02d}/{len(archivos)}] {archivo.name} ...", end=" ")

    # Extraer año y mes del nombre del archivo para el dedup posterior
    parts = archivo.stem.split("_")  # rebuy_final_2024_01 → ['rebuy','final','2024','01']
    anio, mes = int(parts[-2]), int(parts[-1])

    df = pd.read_csv(
        archivo,
        usecols=lambda c: c in COLS + ["nro_trip"],
        low_memory=False
    )

    total_rows_raw += len(df)

    # Solo transacciones de trip 1 (trip 2 viene como columnas)
    df = df[df["nro_trip"] == 1].drop(columns=["nro_trip"], errors="ignore")

    # Agregar columna de fecha del archivo para dedup correcto
    df["archivo_anio"] = anio
    df["archivo_mes"]  = mes

    # Agregar a grano usuario:
    # - Para campos de trip1 que varían por transacción: tomamos el primero (ya están en COLS del trip1)
    # - Para campos de trip2 denormalizados: son iguales en todas las filas del mismo usuario → max
    agg = df.groupby("social_id", sort=False).agg(
        tipo_usuario            = ("tipo_usuario",           "first"),
        fecha_primer_trip       = ("fecha_primer_trip",      "first"),
        fecha_segundo_trip      = ("fecha_segundo_trip",     "first"),
        pais                    = ("pais",                   "first"),
        tipo_viaje              = ("tipo_viaje",             "first"),
        product_type            = ("product_type",           "first"),
        purchase_type           = ("purchase_type",          "first"),
        destino_trip            = ("destino_trip",           "first"),
        origen_trip             = ("origen_trip",            "first"),
        plataforma_trip_1       = ("plataforma_trip_1",      "first"),
        canales_compra_trip_1   = ("canales_compra_trip_1",  "first"),
        flight_class            = ("flight_class",           "first"),
        rango_edad_primer_trip  = ("rango_edad_primer_trip", "first"),
        income                  = ("income",                 "first"),
        bucket_anticipacion_compra = ("bucket_anticipacion_compra", "first"),
        bucket_duracion_viaje   = ("bucket_duracion_viaje",  "first"),
        duracion_viaje_dias     = ("duracion_viaje_dias",    "first"),
        dias_anticipacion_compra_checkin = ("dias_anticipacion_compra_checkin", "first"),
        gross_bookings_usd      = ("gross_bookings_usd",     "sum"),
        flg_uso_cupon           = ("flg_uso_cupon",          "max"),
        flg_tarjeta_credito     = ("flg_tarjeta_credito",    "max"),
        flg_transferencia       = ("flg_transferencia",      "max"),
        flg_puntos_loyalty_pago = ("flg_puntos_loyalty_pago","max"),
        trip_checkin            = ("trip_checkin",            "first"),
        trip_checkout           = ("trip_checkout",           "first"),
        productos_trip_1        = ("productos_trip_1",       "first"),
        # Trip 2
        destino_trip_2          = ("destino_trip_2",         "first"),
        origen_trip_2           = ("origen_trip_2",          "first"),
        tipo_viaje_2            = ("tipo_viaje_2",           "first"),
        productos_trip_2        = ("productos_trip_2",       "first"),
        duracion_viaje_dias_2   = ("duracion_viaje_dias_2",  "first"),
        dias_anticipacion_compra_2 = ("dias_anticipacion_compra_2", "first"),
        gross_bookings_usd_2    = ("gross_bookings_usd_2",   "first"),
        flg_uso_cupon_2         = ("flg_uso_cupon_2",        "first"),
        flight_class_2          = ("flight_class_2",         "first"),
        plataforma_trip_2       = ("plataforma_trip_2",      "first"),
        canales_compra_trip_2   = ("canales_compra_trip_2",  "first"),
        flg_mismo_producto      = ("flg_mismo_producto_trip_1_2", "first"),
        archivo_anio            = ("archivo_anio",               "first"),
        archivo_mes             = ("archivo_mes",                "first"),
    ).reset_index()

    partes.append(agg)
    print(f"{len(agg):,} usuarios")

print(f"\nConcatenando {len(partes)} partes...")
resultado = pd.concat(partes, ignore_index=True)

# Un usuario puede aparecer en varios archivos mensuales
# Nos quedamos con el registro del archivo MAS RECIENTE (estado actual del usuario)
print(f"Antes de dedup: {len(resultado):,} filas")
resultado = resultado.sort_values(["archivo_anio", "archivo_mes"], ascending=False)
resultado = resultado.drop_duplicates(subset="social_id", keep="first")
resultado = resultado.drop(columns=["archivo_anio", "archivo_mes"])
print(f"Después de dedup: {len(resultado):,} usuarios únicos")

# Resumen
print(f"\n=== Distribución tipo_usuario ===")
print(resultado["tipo_usuario"].value_counts())

print(f"\n=== Grupo B con destino_trip_2 conocido ===")
grupo_b = resultado[resultado["tipo_usuario"] == "2 o mas trips"]
print(f"  Total Grupo B: {len(grupo_b):,}")
print(f"  Con destino_trip_2: {grupo_b['destino_trip_2'].notna().sum():,}")
print(f"\n  Top destinos trip2:")
print(grupo_b["destino_trip_2"].value_counts().head(10))

# Guardar
OUTPUT.parent.mkdir(exist_ok=True)
resultado.to_parquet(OUTPUT, index=False)
mb = OUTPUT.stat().st_size / 1024 / 1024
print(f"\nGuardado: {OUTPUT}")
print(f"Tamaño: {mb:.1f} MB")
print(f"Filas: {len(resultado):,}  |  Columnas: {len(resultado.columns)}")

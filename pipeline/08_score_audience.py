"""
FASE 8 - Scoring de audiencia y asignación de recomendaciones.

Para cada usuario en la modeling_view asigna:
  - p_rebuy_18m      : probabilidad predicha por el GBM entrenado en fase 05
  - segmento         : 'alto' / 'medio' / 'bajo' potencial de recompra
  - palanca_1/2      : las dos palancas de activación más importantes que le faltan
  - producto_sugerido: producto a ofrecerle basado en patrones de cross-sell
  - accion_1/2       : texto de acción para CRM

Entrada por defecto: todos los usuarios de modeling_view (CRM filtra su audiencia).
Entrada opcional   : --input CSV con columna social_id para filtrar a un subconjunto.

Salida: recommendations.csv en CACHE_DIR (o --output para ruta custom).

Uso:
  python 08_score_audience.py
  python 08_score_audience.py --input mi_audiencia.csv --output recomendaciones.csv
  python 08_score_audience.py --solo-sin-recompra   # filtra rebuy_ever=0
"""
import argparse
import json
import time
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd

CACHE_DIR     = Path(r"E:\Soporte\Reporting\Rebuy\_cache_v2")
MODELING_PARQUET = CACHE_DIR / "modeling_view.parquet"
MODEL_PATH    = CACHE_DIR / "gbm_rebuy_18m.joblib"
DEFAULT_OUT   = CACHE_DIR / "recommendations.csv"

# ─── Levers de activación (en orden de importancia típica del modelo) ───────
# Cada lever aplica cuando el usuario NO tiene ese atributo (condition=0/False).
LEVERS = [
    {
        "id": "app",
        "feature": "flg_app_90d_antes_trip1",
        "name": "Activar App",
        "action": "Campaña de descarga y activación de App móvil (push/email con deeplink).",
    },
    {
        "id": "puntos",
        "feature": "flg_uso_puntos",
        "name": "Enrollar en Loyalty",
        "action": "Campaña de bienvenida a Despegar+ con bono de puntos en primera redención.",
    },
    {
        "id": "pago",
        "feature": "flg_multi_instrumento_pago",
        "name": "Diversificar medios de pago",
        "action": "Oferta de cuotas sin interés o descuento por primer pago con tarjeta de crédito.",
    },
    {
        "id": "cupon",
        "feature": "flg_uso_cupon",
        "name": "Activar con cupón",
        "action": "Enviar cupón de descuento personalizado (mayor efectividad en segmentos de bajo score).",
    },
]

# ─── Cross-sell por producto del trip 1 ─────────────────────────────────────
CROSSELL = {
    "Vuelos":              "Hotel",
    "Hoteles":             "Vuelos",
    "Carrito":             "Paquete completo (vuelo + hotel)",
    "Actividades":         "Vuelos",
    "Autos":               "Hotel",
    "Traslados":           "Vuelos",
    "Asistencia al viajero": "Paquete de viaje",
    "Bundles":             "Actividades en destino",
}

# ─── Segmentación por score ──────────────────────────────────────────────────
def score_to_segment(p):
    if p >= 0.35:   return "alto"
    if p >= 0.20:   return "medio"
    return "bajo"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def simplify_multivalue(s):
    if s is None:
        return None
    parts = str(s).split(" | ")
    return parts[0] if parts else None


def load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Modelo no encontrado en {MODEL_PATH}. Corré primero pipeline/05_modeling.py."
        )
    bundle = joblib.load(MODEL_PATH)
    log(f"Modelo cargado desde {MODEL_PATH}")
    return bundle


def load_audience(input_csv=None, solo_sin_recompra=False):
    log("Leyendo modeling_view...")
    con = duckdb.connect()
    con.execute("PRAGMA memory_limit='20GB'")
    con.execute("PRAGMA threads=6")

    where_clauses = ["n_transacciones_trip1 IS NOT NULL"]
    if solo_sin_recompra:
        where_clauses.append("rebuy_ever = false")

    where = " AND ".join(where_clauses)

    cols = [
        "social_id",
        "pais", "purchase_type", "plataforma_trip_1", "canales_compra_trip_1",
        "flight_class", "cohort_year", "cohort_month", "tipo_viaje",
        "rango_edad_primer_trip", "income", "bucket_anticipacion_compra",
        "bucket_duracion_viaje",
        "flg_uso_cupon", "flg_uso_puntos", "flg_tarjeta_credito", "flg_transferencia",
        "flg_deposito_bancario", "flg_cash", "flg_multi_instrumento_pago",
        "flg_multi_tipo_pago", "flg_app_90d_antes_trip1", "tiene_vuelo",
        "gross_bookings_usd", "visitas_app_90d_antes_trip1",
        "n_transacciones_trip1", "antiguedad_usuario_dias_al_trip1",
        "rebuy_ever",
    ]
    q = f"SELECT {', '.join(cols)} FROM read_parquet('{MODELING_PARQUET}') WHERE {where}"
    df = con.execute(q).fetchdf()
    log(f"Audiencia cargada: {len(df):,} usuarios")

    if input_csv:
        ids = pd.read_csv(input_csv)["social_id"].astype(str)
        df["social_id"] = df["social_id"].astype(str)
        df = df[df["social_id"].isin(ids)]
        log(f"Filtrado por CSV: {len(df):,} usuarios en la audiencia")

    return df


def engineer_features(df, bundle):
    cat_features = bundle["cat_features"]
    bin_features = bundle["bin_features"]
    num_features = bundle["num_features"]
    cat_levels   = bundle["cat_levels"]

    df = df.copy()
    df["plataforma_principal"] = df["plataforma_trip_1"].apply(simplify_multivalue)
    df["canal_principal"]      = df["canales_compra_trip_1"].apply(simplify_multivalue)
    df["flight_class_simple"]  = df["flight_class"].apply(
        lambda s: "Sin vuelo" if s is None else (simplify_multivalue(s) or "Otro")
    )
    df["log_gross_bookings"] = np.log1p(df["gross_bookings_usd"].clip(lower=0).fillna(0))
    df["visitas_app_90d_antes_trip1"]   = df["visitas_app_90d_antes_trip1"].fillna(0)
    df["antiguedad_usuario_dias_al_trip1"] = df["antiguedad_usuario_dias_al_trip1"].fillna(
        df["antiguedad_usuario_dias_al_trip1"].median()
    )
    for c in ["tipo_viaje", "rango_edad_primer_trip", "income",
              "bucket_anticipacion_compra", "bucket_duracion_viaje"]:
        df[c] = df[c].fillna("Sin dato")
    for b in bin_features:
        df[b] = df[b].fillna(0).astype(int)

    # Aplicar los mismos niveles de categorías que vio el modelo en training
    for c in cat_features:
        known = cat_levels.get(c, [])
        df[c] = df[c].where(df[c].isin(known), other="Otros")
        df[c] = pd.Categorical(df[c], categories=known)

    return df


def assign_levers(row, importance):
    """Devuelve las dos palancas más importantes que le faltan al usuario."""
    candidates = []
    for lever in LEVERS:
        feat = lever["feature"]
        val  = row.get(feat, None)
        if val is not None and int(val) == 0:
            imp = importance.get(feat, 0.0)
            candidates.append((imp, lever["name"], lever["action"]))
    candidates.sort(reverse=True)
    p1 = candidates[0] if len(candidates) > 0 else (0, "Oferta personalizada", "Enviar propuesta de valor personalizada al destino del trip 1.")
    p2 = candidates[1] if len(candidates) > 1 else (0, "Reactivación por email", "Email de reactivación con destinos populares de su perfil.")
    return p1[1], p1[2], p2[1], p2[2]


def assign_product(purchase_type):
    return CROSSELL.get(purchase_type, "Paquete completo")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  default=None, help="CSV con columna social_id")
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    parser.add_argument("--solo-sin-recompra", action="store_true",
                        help="Filtrar solo usuarios que nunca recompraron (rebuy_ever=0)")
    args = parser.parse_args()

    bundle     = load_model()
    gbm        = bundle["model"]
    feat_cols  = bundle["feat_cols"]
    importance = bundle["importance"]

    df_raw = load_audience(input_csv=args.input, solo_sin_recompra=args.solo_sin_recompra)
    df     = engineer_features(df_raw, bundle)

    log("Scoring con GBM...")
    X = df[feat_cols]
    p_rebuy = gbm.predict_proba(X)[:, 1]
    log(f"Score calculado. Media p_rebuy={p_rebuy.mean():.3f}, median={np.median(p_rebuy):.3f}")

    log("Asignando recomendaciones...")
    palanca_1, accion_1, palanca_2, accion_2 = zip(*[
        assign_levers(row, importance) for _, row in df[bundle["bin_features"]].iterrows()
    ])
    producto = df_raw["purchase_type"].apply(assign_product)

    out = pd.DataFrame({
        "social_id":        df_raw["social_id"].values,
        "pais":             df_raw["pais"].values,
        "purchase_type_t1": df_raw["purchase_type"].values,
        "cohort_year":      df_raw["cohort_year"].values,
        "rebuy_ever":       df_raw["rebuy_ever"].values,
        "p_rebuy_18m":      np.round(p_rebuy, 4),
        "segmento":         [score_to_segment(p) for p in p_rebuy],
        "palanca_1":        palanca_1,
        "accion_1":         accion_1,
        "palanca_2":        palanca_2,
        "accion_2":         accion_2,
        "producto_sugerido": producto,
    })

    out_path = Path(args.output)
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    log(f"Guardado: {out_path} ({out_path.stat().st_size/1024:.0f} KB, {len(out):,} filas)")

    # Resumen por segmento
    print("\n── Resumen ──────────────────────────────────────────────────")
    print(out.groupby("segmento")[["p_rebuy_18m"]].agg(["count", "mean"]).to_string())
    print("\n── Top palancas ──────────────────────────────────────────────")
    print(out["palanca_1"].value_counts().to_string())
    print("─────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()

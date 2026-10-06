"""
FASE 4 - Survival analysis (tiempo hasta la 2da compra).

Definicion de duracion/evento (censura administrativa a 36 meses, consistente
con la ventana de poblacion del pipeline SQL):
  T = dias_a_recompra                              si recompro dentro de 36 meses
  T = min(dias observados desde trip1, 36 meses)    si no recompro (censurado)
  E = 1 si recompro dentro de 36 meses, 0 si esta censurado.

Por que 36 meses y no "todo el historico": el propio pipeline excluye del
universo a cualquier usuario cuyo segundo trip conocido ocurrio mas alla de
36 meses (no quedan mal etiquetados como "1 trip"; directamente no estan en la
tabla). Eso significa que, para lo que SI tenemos en esta tabla, ningun sujeto
puede tener un evento "verdadero" mas alla de los 36 meses -> es razonable y
consistente truncar ahi el analisis de supervivencia.

Se corre Kaplan-Meier general y por subgrupos, con log-rank test para cada
comparacion. Salida compacta: puntos de la curva muestreados en una grilla de
dias (no el step function completo) para que el JSON sea liviano.
"""
import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from lifelines import KaplanMeierFitter
from lifelines.statistics import multivariate_logrank_test

CACHE_DIR = Path(r"E:\Soporte\Reporting\Rebuy\_cache_v2")
MODELING_PARQUET = CACHE_DIR / "modeling_view.parquet"
PROJECT_DIR = Path(__file__).resolve().parent.parent
OUT_JSON = PROJECT_DIR / "pipeline" / "_fragment_survival.json"

MAX_DAYS = 1096  # 36 meses (administrativo)
TIME_GRID = sorted(set(list(range(0, 31, 5)) + list(range(30, 181, 15)) + list(range(180, MAX_DAYS + 1, 30)) + [365, 730, 1096]))


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_data():
    con = duckdb.connect()
    con.execute("PRAGMA disable_progress_bar")
    con.execute("PRAGMA memory_limit='20GB'")
    con.execute("PRAGMA threads=6")
    df = con.execute(f"""
        SELECT
            CASE WHEN rebuy_ever AND dias_a_recompra <= {MAX_DAYS} THEN dias_a_recompra
                 ELSE LEAST(dias_observados_desde_trip1, {MAX_DAYS}) END AS T,
            CASE WHEN rebuy_ever AND dias_a_recompra <= {MAX_DAYS} THEN 1 ELSE 0 END AS E,
            pais, flg_app_90d_antes_trip1, purchase_type, plataforma_trip_1, flg_uso_puntos
        FROM read_parquet('{MODELING_PARQUET}')
        WHERE n_transacciones_trip1 IS NOT NULL
    """).fetchdf()
    return df


def km_curve(df, mask=None):
    sub = df if mask is None else df[mask]
    kmf = KaplanMeierFitter()
    kmf.fit(sub["T"], sub["E"])
    sf = kmf.survival_function_at_times(TIME_GRID)
    return {
        "n": int(len(sub)), "n_eventos": int(sub["E"].sum()),
        "t": TIME_GRID, "s": [round(float(v), 4) for v in sf.values],
    }


def group_km(df, group_col, top_n=6, min_n=3000):
    vc = df[group_col].value_counts()
    top_vals = [v for v in vc.index[:top_n] if vc[v] >= min_n and pd.notna(v)]
    curves = {}
    for v in top_vals:
        curves[str(v)] = km_curve(df, df[group_col] == v)
    valid = df[df[group_col].isin(top_vals)]
    p = None
    if len(top_vals) >= 2:
        try:
            res = multivariate_logrank_test(valid["T"], valid[group_col], valid["E"])
            p = float(res.p_value)
        except Exception as e:
            p = None
    return {"curves": curves, "logrank_p": p}


def main():
    log("Cargando datos de duracion/evento...")
    df = load_data()
    log(f"n={len(df):,}, eventos={int(df['E'].sum()):,}")

    out = {"time_grid": TIME_GRID, "max_days": MAX_DAYS}

    log("KM general...")
    out["general"] = km_curve(df)

    log("KM por App (90d antes de trip1)...")
    out["por_app"] = group_km(df, "flg_app_90d_antes_trip1", top_n=2)

    log("KM por país (top 6)...")
    out["por_pais"] = group_km(df, "pais", top_n=6)

    log("KM por producto (top 5)...")
    out["por_producto"] = group_km(df, "purchase_type", top_n=5)

    log("KM por plataforma trip1 (top 4)...")
    out["por_plataforma"] = group_km(df, "plataforma_trip_1", top_n=4)

    log("KM por uso de loyalty...")
    out["por_loyalty"] = group_km(df, "flg_uso_puntos", top_n=2)

    def npconv(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if np.isnan(o) else float(o)
        if pd.isna(o):
            return None
        return str(o)

    OUT_JSON.write_text(json.dumps(out, default=npconv, ensure_ascii=False), encoding="utf-8")
    log(f"Guardado {OUT_JSON} ({OUT_JSON.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()

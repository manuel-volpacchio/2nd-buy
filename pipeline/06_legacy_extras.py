"""
FASE 6 - Recalcula, sobre la base v2 (con las variables nuevas), los cortes que
ya existian en el dashboard v1 y seguian siendo validos: velocidad de recompra +
engagement (Grupo C, solo descriptivo "entre quienes recompraron"), transiciones
de producto/canal/plataforma entre trip1 y trip2, efecto cupon en trip1 y uso de
cupon en trip2. No se descarta este trabajo previo, se lo re-corre sobre datos
mas ricos y con la grilla de dedup correcta (ver 01/02).
"""
import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

CACHE_DIR = Path(r"E:\Soporte\Reporting\Rebuy\_cache_v2")
MODELING_PARQUET = CACHE_DIR / "modeling_view.parquet"
TX_PARQUET = CACHE_DIR / "tx_level.parquet"
PROJECT_DIR = Path(__file__).resolve().parent.parent
OUT_JSON = PROJECT_DIR / "pipeline" / "_fragment_legacy.json"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    con = duckdb.connect()
    con.execute("PRAGMA disable_progress_bar")
    con.execute("PRAGMA memory_limit='20GB'")
    con.execute("PRAGMA threads=6")
    con.execute(f"CREATE OR REPLACE VIEW mv AS SELECT * FROM read_parquet('{MODELING_PARQUET}')")
    con.execute(f"CREATE OR REPLACE VIEW tx AS SELECT * FROM read_parquet('{TX_PARQUET}')")

    out = {}

    log("Speed buckets (velocidad de recompra + engagement, entre recompradores)...")
    df = con.execute("""
        SELECT
            CASE
                WHEN dias_a_recompra <= 7 THEN '0-7d'
                WHEN dias_a_recompra <= 30 THEN '8-30d'
                WHEN dias_a_recompra <= 90 THEN '31-90d'
                WHEN dias_a_recompra <= 180 THEN '91-180d'
                WHEN dias_a_recompra <= 365 THEN '181-365d'
                ELSE '>365d'
            END AS speed_bucket,
            count(*) n_usuarios,
            avg(dias_a_recompra) avg_dias,
            avg(cantidad_visitas_entre_trips) avg_visitas,
            avg(cantidad_searches_entre_trips) avg_searches,
            sum(eventos_directo) ev_directo, sum(eventos_sem_seo_kwbrand) ev_seo,
            sum(eventos_metabuscadores) ev_meta, sum(eventos_crm) ev_crm, sum(eventos_otros) ev_otros
        FROM mv WHERE rebuy_ever
        GROUP BY 1
    """).fetchdf()
    order = ["0-7d", "8-30d", "31-90d", "91-180d", "181-365d", ">365d"]
    df["ord"] = df["speed_bucket"].apply(lambda x: order.index(x))
    df = df.sort_values("ord").drop(columns="ord")
    out["speedBuckets"] = df.to_dict(orient="list")

    log("Lealtad de producto por categoria...")
    df = con.execute("""
        SELECT purchase_type AS producto_trip1, count(*) n_rebuyers,
            sum(flg_mismo_producto_trip_1_2) n_mismo_producto
        FROM mv WHERE rebuy_ever AND n_transacciones_trip1 IS NOT NULL
        GROUP BY 1 ORDER BY n_rebuyers DESC
    """).fetchdf()
    out["sameProductByCategory"] = df.to_dict(orient="list")

    log("Transiciones producto / canal / plataforma...")
    out["productTransition"] = con.execute("""
        SELECT productos_trip_1, productos_trip_2, count(*) n
        FROM mv WHERE rebuy_ever GROUP BY 1,2 ORDER BY n DESC LIMIT 12
    """).fetchdf().to_dict(orient="list")
    out["canalTransition"] = con.execute("""
        SELECT canales_compra_trip_1 AS canal_trip_1, canales_compra_trip_2 AS canal_trip_2, count(*) n
        FROM mv WHERE rebuy_ever GROUP BY 1,2 ORDER BY n DESC LIMIT 15
    """).fetchdf().to_dict(orient="list")
    out["plataformaTransition"] = con.execute("""
        SELECT plataforma_trip_1, plataforma_trip_2, count(*) n
        FROM mv WHERE rebuy_ever GROUP BY 1,2 ORDER BY n DESC LIMIT 15
    """).fetchdf().to_dict(orient="list")

    log("Cupon trip2 (entre quienes recompraron)...")
    df = con.execute("""
        WITH trip2_tx AS (
            SELECT social_id, arg_min(flg_uso_cupon, reservation_datetime) AS flg_uso_cupon_trip2
            FROM tx WHERE nro_trip = 2 GROUP BY social_id
        )
        SELECT flg_uso_cupon_trip2, count(*) n_rebuyers
        FROM trip2_tx GROUP BY 1
    """).fetchdf()
    out["cuponTrip2Usage"] = df.to_dict(orient="list")

    log("Lealtad de destino y temporada del viaje (pedido de Maria Sol, 2026-09-21)...")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE trip2_viaje AS
        SELECT social_id,
            arg_min(destino_trip, reservation_datetime) AS destino_trip2,
            arg_min(trip_checkin, reservation_datetime) AS checkin_trip2
        FROM tx WHERE nro_trip = 2
        GROUP BY social_id
    """)
    con.execute("""
        CREATE OR REPLACE TEMP TABLE viaje_join AS
        SELECT m.social_id, m.destino_trip AS destino_trip1, m.trip_checkin AS checkin_trip1,
            t2.destino_trip2, t2.checkin_trip2,
            (m.destino_trip = t2.destino_trip2) AS flg_mismo_destino,
            (month(m.trip_checkin) = month(t2.checkin_trip2)) AS flg_mismo_mes_viaje,
            (ceil(month(m.trip_checkin)/3.0) = ceil(month(t2.checkin_trip2)/3.0)) AS flg_mismo_trimestre_viaje
        FROM mv m
        INNER JOIN trip2_viaje t2 ON m.social_id = t2.social_id
        WHERE m.rebuy_ever AND m.destino_trip IS NOT NULL AND t2.destino_trip2 IS NOT NULL
            AND m.trip_checkin IS NOT NULL AND t2.checkin_trip2 IS NOT NULL
    """)

    df = con.execute("""
        SELECT destino_trip1, count(*) n_rebuyers, sum(CASE WHEN flg_mismo_destino THEN 1 ELSE 0 END) n_mismo_destino
        FROM viaje_join GROUP BY 1 HAVING count(*) >= 1000 ORDER BY n_rebuyers DESC LIMIT 15
    """).fetchdf()
    out["sameDestinoByTop"] = df.to_dict(orient="list")

    out["destinoTransition"] = con.execute("""
        SELECT destino_trip1, destino_trip2, count(*) n
        FROM viaje_join GROUP BY 1,2 ORDER BY n DESC LIMIT 15
    """).fetchdf().to_dict(orient="list")

    # Mes de VIAJE (trip_checkin, no fecha de compra) de trip1 vs trip2, para poder ver el
    # patron de estacionalidad ano contra ano (independiente de en que ano calendario cayo).
    log("Matriz mes de viaje (check-in) trip1 x trip2...")
    out["mesViajeMatrix"] = con.execute("""
        SELECT month(checkin_trip1) AS mes_trip1, month(checkin_trip2) AS mes_trip2, count(*) n
        FROM viaje_join GROUP BY 1,2 ORDER BY 1,2
    """).fetchdf().to_dict(orient="list")

    row = con.execute("""
        SELECT count(*) n_rebuyers,
            sum(CASE WHEN flg_mismo_destino THEN 1 ELSE 0 END) n_mismo_destino,
            sum(CASE WHEN flg_mismo_mes_viaje THEN 1 ELSE 0 END) n_mismo_mes,
            sum(CASE WHEN flg_mismo_trimestre_viaje THEN 1 ELSE 0 END) n_mismo_trimestre
        FROM viaje_join
    """).fetchdf().iloc[0]
    out["lealtadDestinoTemporada"] = {
        "n_rebuyers": int(row.n_rebuyers),
        "pct_mismo_destino": float(row.n_mismo_destino) / float(row.n_rebuyers),
        "pct_mismo_mes": float(row.n_mismo_mes) / float(row.n_rebuyers),
        "pct_mismo_trimestre": float(row.n_mismo_trimestre) / float(row.n_rebuyers),
    }

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

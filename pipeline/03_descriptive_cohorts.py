"""
FASE 3 - Descriptivos, cohortes y cortes por segmento.

Regla general aplicada en todo este script: la metrica principal de comparacion
es SIEMPRE "tasa de recompra a 12 meses" (rebuy_12m) calculada SOLO sobre
eligible_12m = True (cohortes que ya tuvieron 12 meses completos para recomprar).
Se descartan segmentos con menos de MIN_SEGMENT usuarios elegibles para evitar
conclusiones sobre bases chicas. Cuando corresponde (path de medios, CS,
economics de margen) se restringe ademas por cohorte valida segun el
diccionario de variables (ver variable_dictionary.py).

Salida: descriptive.json (fragmento que despues se mergea al payload del dashboard).
"""
import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

CACHE_DIR = Path(r"E:\Soporte\Reporting\Rebuy\_cache_v2")
MODELING_PARQUET = CACHE_DIR / "modeling_view.parquet"
PROJECT_DIR = Path(__file__).resolve().parent.parent
OUT_JSON = PROJECT_DIR / "pipeline" / "_fragment_descriptive.json"

MIN_SEGMENT = 300
HORIZONS = [6, 12, 18, 24, 36]
STANDARD_HORIZON = 18  # a pedido de Matias (2026-09-21): estandar de retention para viajes

# Misma taxonomia que usa el SQL fuente (seccion "10. PATH DE MEDIOS POR TRANSACCION")
# para agrupar event_type en 5 canales. Se replica aca para poder clasificar
# first_click_event_type / last_click_event_type con el mismo criterio que
# eventos_directo/crm/sem_seo_kwbrand/metabuscadores/otros, y que los cortes sean
# comparables entre si.
CRM_EVENTS = "('EMAIL','COM_EMAIL','PUSH','COM_PUSH','WEB_PUSH','COM_WHATSAPP','SEM_WHATSAPP','SOCIAL_WHATSAPP','ERROR_EMAIL','ERROR_PUSH','ERROR_WEB_PUSH')"
META_EVENTS = "('SEM_SKYSCANNER','SEM_TRIVAGO','SEM_TRIPADVISOR','SEM_TURISMOCITY','SEM_METASEARCH','SEM_KAYAK','SEM_MUNDI','SEM_HOTELS','SEM_HOTELS_COMBINED','SEO_GOOGLE_FLIGHTS','SEO_GOOGLE_HOTELS','ERROR_SEM_SKYSCANNER','ERROR_SEM_TRIVAGO','ERROR_SEM_TRIPADVISOR','ERROR_SEM_METASEARCH','ERROR_SEM_KAYAK','ERROR_SEM_MUNDI','ERROR_SEM_HOTELS','ERROR_SEM_HOTELS_COMBINED')"


def event_taxonomy_expr(col):
    return f"""CASE
        WHEN {col} = 'MANUAL_ENTRY' THEN 'Directo'
        WHEN {col} IN {CRM_EVENTS} THEN 'CRM'
        WHEN {col} IN {META_EVENTS} THEN 'Metabuscadores'
        WHEN {col} LIKE 'SEO_%' THEN 'SEM/SEO/KWBrand'
        WHEN {col} LIKE 'SEM_%' THEN 'SEM/SEO/KWBrand'
        WHEN {col} LIKE 'BND_%' THEN 'SEM/SEO/KWBrand'
        WHEN {col} LIKE 'ERROR_SEM_%' THEN 'SEM/SEO/KWBrand'
        WHEN {col} IS NULL THEN NULL
        ELSE 'Otros'
    END"""


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def get_con():
    con = duckdb.connect()
    con.execute("PRAGMA disable_progress_bar")
    con.execute("PRAGMA memory_limit='20GB'")
    con.execute("PRAGMA threads=6")
    con.execute(f"CREATE OR REPLACE VIEW mv AS SELECT * FROM read_parquet('{MODELING_PARQUET}')")
    return con


def categorical_breakdown(con, dim_expr, label, extra_where="TRUE", horizon=18):
    q = f"""
        SELECT {dim_expr} AS categoria,
            count(*) AS n_usuarios,
            sum(CASE WHEN rebuy_{horizon}m THEN 1 ELSE 0 END) AS n_rebuy,
            sum(CASE WHEN rebuy_{horizon}m THEN 1 ELSE 0 END)::DOUBLE / count(*) AS rate
        FROM mv
        WHERE eligible_{horizon}m AND n_transacciones_trip1 IS NOT NULL AND ({extra_where})
        GROUP BY 1
        HAVING count(*) >= {MIN_SEGMENT}
        ORDER BY rate DESC
    """
    df = con.execute(q).fetchdf()
    return {"label": label, "horizon": horizon, "rows": df.to_dict(orient="records")}


def continuous_bins(con, var, bin_expr, label, extra_where="TRUE", horizon=18):
    q = f"""
        SELECT {bin_expr} AS bucket,
            count(*) AS n_usuarios,
            sum(CASE WHEN rebuy_{horizon}m THEN 1 ELSE 0 END) AS n_rebuy,
            sum(CASE WHEN rebuy_{horizon}m THEN 1 ELSE 0 END)::DOUBLE / count(*) AS rate,
            avg({var}) AS avg_valor
        FROM mv
        WHERE eligible_{horizon}m AND n_transacciones_trip1 IS NOT NULL AND ({extra_where})
        GROUP BY 1
        HAVING count(*) >= {MIN_SEGMENT}
        ORDER BY min({var})
    """
    df = con.execute(q).fetchdf()
    return {"label": label, "horizon": horizon, "rows": df.to_dict(orient="records")}


def distribution_by_target(con, var, extra_where="TRUE", horizon=18):
    q = f"""
        SELECT rebuy_{horizon}m AS rebuy,
            count(*) n,
            approx_quantile({var}, 0.10) p10,
            approx_quantile({var}, 0.25) p25,
            approx_quantile({var}, 0.50) p50,
            approx_quantile({var}, 0.75) p75,
            approx_quantile({var}, 0.90) p90,
            avg({var}) media
        FROM mv
        WHERE eligible_{horizon}m AND n_transacciones_trip1 IS NOT NULL AND ({extra_where}) AND {var} IS NOT NULL
        GROUP BY 1
    """
    df = con.execute(q).fetchdf()
    return df.to_dict(orient="records")


def main():
    con = get_con()
    out = {}

    log("KPIs globales por horizonte...")
    kpi_rows = []
    for h in HORIZONS:
        r = con.execute(f"""
            SELECT count(*) n_eligible, sum(CASE WHEN rebuy_{h}m THEN 1 ELSE 0 END) n_rebuy
            FROM mv WHERE eligible_{h}m
        """).fetchdf().iloc[0]
        kpi_rows.append({"horizon": h, "n_eligible": int(r.n_eligible), "n_rebuy": int(r.n_rebuy),
                          "rate": float(r.n_rebuy) / float(r.n_eligible)})
    out["kpis_por_horizonte"] = kpi_rows

    total = con.execute("SELECT count(*) n, sum(CASE WHEN rebuy_ever THEN 1 ELSE 0 END) r FROM mv").fetchdf().iloc[0]
    dias = con.execute("SELECT median(dias_a_recompra) med, avg(dias_a_recompra) avg FROM mv WHERE rebuy_ever").fetchdf().iloc[0]
    out["kpis_generales"] = {
        "n_total": int(total.n), "n_rebuy_ever": int(total.r),
        "rate_ever": float(total.r) / float(total.n),
        "mediana_dias_a_recompra": float(dias.med), "promedio_dias_a_recompra": float(dias.avg),
    }

    log(f"Cortes categoricos ({STANDARD_HORIZON}m)...")
    out["por_pais"] = categorical_breakdown(con, "pais", "País")
    out["por_producto"] = categorical_breakdown(con, "purchase_type", "Producto (purchase_type trip1)")
    out["por_plataforma"] = categorical_breakdown(con, "plataforma_trip_1", "Plataforma trip1 (puede ser multivalor)")
    out["por_canal"] = categorical_breakdown(con, "canales_compra_trip_1", "Canal de compra trip1")
    out["por_flight_class"] = categorical_breakdown(con, "flight_class", "Flight class (solo Vuelos)", extra_where="flight_class IS NOT NULL")
    out["por_cupon"] = categorical_breakdown(con, "flg_uso_cupon", "Uso de cupón trip1")
    out["por_uso_puntos"] = categorical_breakdown(con, "flg_uso_puntos", "Uso de puntos loyalty trip1")
    out["por_tier_loyalty"] = categorical_breakdown(con, "tier_al_momento_redencion", "Tier loyalty (solo con redención)", extra_where="tier_al_momento_redencion IS NOT NULL")
    out["por_tarjeta_credito"] = categorical_breakdown(con, "flg_tarjeta_credito", "Pagó con tarjeta de crédito")
    out["por_transferencia"] = categorical_breakdown(con, "flg_transferencia", "Pagó con transferencia")
    out["por_multi_instrumento"] = categorical_breakdown(con, "flg_multi_instrumento_pago", "Usó más de un instrumento de pago")
    out["por_app_antes"] = categorical_breakdown(con, "flg_app_90d_antes_trip1", "Usó App en los 90d antes de trip1")
    out["por_tiene_vuelo"] = categorical_breakdown(con, "tiene_vuelo", "Trip1 incluyó vuelo")
    out["por_customer_service"] = categorical_breakdown(
        con, "flg_customer_service", "Tuvo interacción de Customer Service en trip1",
        extra_where="cohort_year >= '2024'")
    out["por_cs_satisfaccion"] = categorical_breakdown(
        con, "CASE WHEN flg_cs_satisfecho=1 THEN 'Satisfecho' WHEN flg_cs_insatisfecho=1 THEN 'Insatisfecho' ELSE 'Neutro/NA' END",
        "Satisfacción CS (solo con interacción, cohortes 2024+)",
        extra_where="cohort_year >= '2024' AND flg_customer_service = 1")

    log("Grafico dedicado: recompra por cantidad de transacciones en trip1 (pedido de Matias)...")
    out["por_n_transacciones_trip1"] = categorical_breakdown(
        con, "CASE WHEN n_transacciones_trip1=1 THEN '1 transacción' WHEN n_transacciones_trip1=2 THEN '2 transacciones' ELSE '3 o más' END",
        "Recompra por cantidad de transacciones dentro de trip1", extra_where="TRUE")

    log("Cortes demograficos y de perfil de usuario (variables nuevas)...")
    out["por_tipo_viaje"] = categorical_breakdown(con, "tipo_viaje", "Tipo de viaje (nacional/internacional)")
    out["por_rango_edad"] = categorical_breakdown(con, "rango_edad_primer_trip", "Rango de edad al momento de trip1")
    out["por_income"] = categorical_breakdown(con, "income", "Nivel de ingreso estimado")
    out["por_nationality"] = categorical_breakdown(con, "nationality", "Nacionalidad")
    out["por_pais_residencia"] = categorical_breakdown(con, "pais_residencia", "País de residencia (puede diferir del país de la compra)")
    out["por_bucket_anticipacion"] = categorical_breakdown(con, "bucket_anticipacion_compra", "Anticipación de compra (días entre reserva y check-in)")
    out["por_bucket_duracion"] = categorical_breakdown(con, "bucket_duracion_viaje", "Duración del viaje")
    out["por_pais_vs_residencia_igual"] = categorical_breakdown(
        con, "CASE WHEN pais = pais_residencia THEN 'Viajó dentro de su país de residencia' ELSE 'Viajó fuera de su país de residencia' END",
        "¿El país del viaje coincide con el país de residencia?", extra_where="pais_residencia IS NOT NULL")

    log("Bins de antigüedad de cuenta (dosis-respuesta, variable nueva)...")
    out["bin_antiguedad_usuario"] = continuous_bins(
        con, "antiguedad_usuario_dias_al_trip1",
        "CASE WHEN antiguedad_usuario_dias_al_trip1=0 THEN '0 (mismo día)' "
        "WHEN antiguedad_usuario_dias_al_trip1<=30 THEN '1-30 días' "
        "WHEN antiguedad_usuario_dias_al_trip1<=180 THEN '31-180 días' "
        "WHEN antiguedad_usuario_dias_al_trip1<=365 THEN '181-365 días' "
        "WHEN antiguedad_usuario_dias_al_trip1<=1095 THEN '1-3 años' ELSE '3+ años' END",
        "Antigüedad de la cuenta al momento de trip1")

    log("Cortes de path de medios (solo cohortes 2021+)...")
    out["por_canal_dominante_path"] = categorical_breakdown(
        con,
        """CASE
            WHEN eventos_path_total = 0 OR eventos_path_total IS NULL THEN 'Sin path registrado'
            WHEN eventos_directo >= greatest(eventos_sem_seo_kwbrand, eventos_metabuscadores, eventos_crm, eventos_otros) THEN 'Directo'
            WHEN eventos_sem_seo_kwbrand >= greatest(eventos_directo, eventos_metabuscadores, eventos_crm, eventos_otros) THEN 'SEM/SEO/KWBrand'
            WHEN eventos_metabuscadores >= greatest(eventos_directo, eventos_sem_seo_kwbrand, eventos_crm, eventos_otros) THEN 'Metabuscadores'
            WHEN eventos_crm >= greatest(eventos_directo, eventos_sem_seo_kwbrand, eventos_metabuscadores, eventos_otros) THEN 'CRM'
            ELSE 'Otros'
        END""",
        "Canal dominante del path de atribución de trip1 (cohortes 2021+)",
        extra_where="cohorte_con_path_medios_valido")

    log("Cortes de first click / last click (solo cohortes 2021+)...")
    out["por_first_click_canal"] = categorical_breakdown(
        con, event_taxonomy_expr("first_click_event_type"),
        "Canal del primer click del path de trip1 (cohortes 2021+)",
        extra_where="cohorte_con_path_medios_valido AND first_click_event_type IS NOT NULL")
    out["por_last_click_canal"] = categorical_breakdown(
        con, event_taxonomy_expr("last_click_event_type"),
        "Canal del último click antes de comprar trip1 (cohortes 2021+)",
        extra_where="cohorte_con_path_medios_valido AND last_click_event_type IS NOT NULL")
    out["por_first_last_mismo_canal"] = categorical_breakdown(
        con,
        f"CASE WHEN {event_taxonomy_expr('first_click_event_type')} = {event_taxonomy_expr('last_click_event_type')} THEN 'Mismo canal (first=last)' ELSE 'Canal distinto (multi-touch)' END",
        "¿El primer y último click de trip1 fueron del mismo canal? (cohortes 2021+)",
        extra_where="cohorte_con_path_medios_valido AND first_click_event_type IS NOT NULL AND last_click_event_type IS NOT NULL")

    log("Bins de variables continuas (12m)...")
    out["bin_visitas_app_antes"] = continuous_bins(
        con, "visitas_app_90d_antes_trip1",
        "CASE WHEN visitas_app_90d_antes_trip1=0 THEN '0' WHEN visitas_app_90d_antes_trip1=1 THEN '1' "
        "WHEN visitas_app_90d_antes_trip1<=3 THEN '2-3' WHEN visitas_app_90d_antes_trip1<=7 THEN '4-7' "
        "WHEN visitas_app_90d_antes_trip1<=15 THEN '8-15' ELSE '16+' END",
        "Visitas App en 90d antes de trip1 (dosis-respuesta)")
    out["bin_gross_bookings"] = continuous_bins(
        con, "gross_bookings_usd",
        "CASE WHEN gross_bookings_usd<100 THEN '<100' WHEN gross_bookings_usd<250 THEN '100-250' "
        "WHEN gross_bookings_usd<500 THEN '250-500' WHEN gross_bookings_usd<1000 THEN '500-1000' "
        "WHEN gross_bookings_usd<2500 THEN '1000-2500' ELSE '2500+' END",
        "Gross bookings USD de trip1", extra_where="gross_bookings_usd IS NOT NULL AND gross_bookings_usd > 0")
    out["bin_n_transacciones_trip1"] = continuous_bins(
        con, "n_transacciones_trip1",
        "CASE WHEN n_transacciones_trip1=1 THEN '1' WHEN n_transacciones_trip1=2 THEN '2' ELSE '3+' END",
        "Cantidad de transacciones dentro de trip1")

    log("Distribuciones (percentiles) por target...")
    out["dist_gross_bookings_por_target"] = distribution_by_target(con, "gross_bookings_usd", extra_where="gross_bookings_usd > 0")
    out["dist_visitas_app_por_target"] = distribution_by_target(con, "visitas_app_90d_antes_trip1")

    log("Interacciones clave (2 vías)...")
    def interaction(dim_a, dim_b, label):
        q = f"""
            SELECT {dim_a} AS a, {dim_b} AS b, count(*) n,
                sum(CASE WHEN rebuy_12m THEN 1 ELSE 0 END)::DOUBLE / count(*) AS rate
            FROM mv WHERE eligible_12m AND n_transacciones_trip1 IS NOT NULL
            GROUP BY 1,2 HAVING count(*) >= {MIN_SEGMENT}
        """
        df = con.execute(q).fetchdf()
        return {"label": label, "rows": df.to_dict(orient="records")}

    out["interaccion_app_x_puntos"] = interaction("flg_app_90d_antes_trip1", "flg_uso_puntos", "App x Uso de puntos loyalty")
    out["interaccion_app_x_tarjeta"] = interaction("flg_app_90d_antes_trip1", "flg_tarjeta_credito", "App x Tarjeta de crédito")
    out["interaccion_app_x_pais"] = interaction("flg_app_90d_antes_trip1", "pais", "App x País")
    out["interaccion_app_x_producto"] = interaction("flg_app_90d_antes_trip1", "purchase_type", "App x Producto")
    out["interaccion_app_x_cohort_year"] = interaction("flg_app_90d_antes_trip1", "cohort_year", "App x Año de cohorte (para desconfundir tendencia temporal)")

    log("Cohortes: tasa de recompra por cohorte de trip1 y horizonte...")
    cohort_rows = []
    for h in HORIZONS:
        df = con.execute(f"""
            SELECT cohort_year, count(*) n, sum(CASE WHEN eligible_{h}m THEN 1 ELSE 0 END) n_elig,
                sum(CASE WHEN eligible_{h}m AND rebuy_{h}m THEN 1 ELSE 0 END) n_rebuy
            FROM mv GROUP BY 1 ORDER BY 1
        """).fetchdf()
        df["horizon"] = h
        cohort_rows.append(df)
    out["cohortes_por_anio"] = pd.concat(cohort_rows).to_dict(orient="records")

    df_month = con.execute(f"""
        SELECT cohort_month, count(*) n, sum(CASE WHEN eligible_{STANDARD_HORIZON}m THEN 1 ELSE 0 END) n_elig,
            sum(CASE WHEN eligible_{STANDARD_HORIZON}m AND rebuy_{STANDARD_HORIZON}m THEN 1 ELSE 0 END) n_rebuy
        FROM mv GROUP BY 1 ORDER BY 1
    """).fetchdf()
    out["cohortes_por_mes_estandar"] = df_month.to_dict(orient="records")
    out["standard_horizon"] = STANDARD_HORIZON

    log("Tabla de cohortes por país y uso de puntos (pedido de Matías, 2026-09-21)...")
    out["cohortesPaisPuntos"] = con.execute(f"""
        SELECT cohort_year, pais,
            CASE WHEN flg_uso_puntos=1 THEN 'Con puntos' ELSE 'Sin puntos' END AS uso_puntos,
            count(*) n_usuarios,
            sum(CASE WHEN eligible_{STANDARD_HORIZON}m THEN 1 ELSE 0 END) n_elegibles,
            sum(CASE WHEN eligible_{STANDARD_HORIZON}m AND rebuy_{STANDARD_HORIZON}m THEN 1 ELSE 0 END) n_rebuy
        FROM mv
        WHERE n_transacciones_trip1 IS NOT NULL
        GROUP BY 1,2,3
        HAVING count(*) >= 50
        ORDER BY cohort_year, pais, uso_puntos
    """).fetchdf().to_dict(orient="list")

    log("Segmentos por año de cohorte (filtro por fecha de trip1, pedido Matías 2026-09-22)...")
    # Mapeo año → horizonte estándar más maduro disponible para ese año
    YEAR_HORIZON = {2022: 18, 2023: 18, 2024: 12, 2025: 6}
    YEAR_DIMS = [
        ("purchase_type", "por_producto"),
        ("pais", "por_pais"),
        ("flg_app_90d_antes_trip1", "por_app_antes"),
        ("flg_uso_puntos", "por_uso_puntos"),
        ("CASE WHEN n_transacciones_trip1=1 THEN '1 transacción' WHEN n_transacciones_trip1=2 THEN '2 transacciones' ELSE '3 o más' END", "por_n_transacciones_trip1"),
        ("plataforma_trip_1", "por_plataforma"),
    ]
    year_segs = {}
    for year, h in YEAR_HORIZON.items():
        year_segs[str(year)] = {}
        for dim_expr, dim_key in YEAR_DIMS:
            df_y = con.execute(f"""
                SELECT {dim_expr} AS categoria, count(*) n_usuarios,
                    sum(CASE WHEN rebuy_{h}m THEN 1 ELSE 0 END) n_rebuy,
                    sum(CASE WHEN rebuy_{h}m THEN 1 ELSE 0 END)::DOUBLE / count(*) AS rate
                FROM mv
                WHERE eligible_{h}m AND n_transacciones_trip1 IS NOT NULL AND cohort_year = {year}
                GROUP BY 1 HAVING count(*) >= 100 ORDER BY rate DESC
            """).fetchdf()
            year_segs[str(year)][dim_key] = {"horizon": h, "rows": df_y.to_dict(orient="records")}
    out["por_anio_segments"] = year_segs

    log("Cubo multi-dimensional para explorador de cohortes (pedido 2026-09-22)...")
    TX_PARQUET = str(CACHE_DIR / "tx_level.parquet")
    # Obtener top-N para bucketear categorias raras
    top_paises      = [r[0] for r in con.execute("SELECT pais FROM mv WHERE n_transacciones_trip1 IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC LIMIT 8").fetchall() if r[0] is not None]
    top_productos   = [r[0] for r in con.execute("SELECT purchase_type FROM mv WHERE n_transacciones_trip1 IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC LIMIT 6").fetchall() if r[0] is not None]
    top_plat        = [r[0] for r in con.execute("SELECT plataforma_trip_1 FROM mv WHERE n_transacciones_trip1 IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC LIMIT 4").fetchall() if r[0] is not None]
    top_canal       = [r[0] for r in con.execute("SELECT canales_compra_trip_1 FROM mv WHERE n_transacciones_trip1 IS NOT NULL AND canales_compra_trip_1 IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC LIMIT 5").fetchall() if r[0] is not None]
    top_productos_t2 = [r[0] for r in con.execute("""
        SELECT SPLIT_PART(productos_trip_2, ' | ', 1) AS p2, count(*) n
        FROM mv
        WHERE productos_trip_2 IS NOT NULL AND n_transacciones_trip1 IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 7
    """).fetchall() if r[0] is not None]
    # Top city codes (IATA) por volumen de reservas — se usan directamente en el cubo,
    # sin colapsar a país. Top 20 para T1 y T2 por separado, el resto va a 'Otros'.
    top_destinos_t1 = [r[0] for r in con.execute(f"""
        SELECT destino_trip, COUNT(*) n
        FROM read_parquet('{TX_PARQUET}')
        WHERE nro_trip = 1 AND destino_trip IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 20
    """).fetchall() if r[0] is not None]
    top_destinos_t2 = [r[0] for r in con.execute(f"""
        SELECT destino_trip, COUNT(*) n
        FROM read_parquet('{TX_PARQUET}')
        WHERE nro_trip = 2 AND destino_trip IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 20
    """).fetchall() if r[0] is not None]
    # Codificar listas para SQL (escapar comillas simples)
    def _sql_list(lst):
        return "', '".join(str(x).replace("'", "''") for x in lst)
    # Destino del 2do trip: un registro por social_id (la reserva con mayor volumen de nro_trip=2)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE t2_dest AS
        SELECT social_id, FIRST(destino_trip ORDER BY 1) AS destino_t2_iata
        FROM read_parquet('{TX_PARQUET}')
        WHERE nro_trip = 2 AND destino_trip IS NOT NULL
        GROUP BY 1
    """)
    df_cube = con.execute(f"""
        SELECT
            mv.cohort_year,
            EXTRACT(MONTH FROM mv.fecha_primer_trip)::INTEGER AS cohort_month,
            CASE WHEN mv.destino_trip IN ('{_sql_list(top_destinos_t1)}') THEN mv.destino_trip ELSE 'Otros' END AS destino_t1,
            CASE WHEN mv.pais IN ('{_sql_list(top_paises)}') THEN mv.pais ELSE 'Otros' END AS pais,
            CASE WHEN mv.purchase_type IN ('{_sql_list(top_productos)}') THEN mv.purchase_type ELSE 'Otros' END AS producto_t1,
            CASE WHEN mv.plataforma_trip_1 IN ('{_sql_list(top_plat)}') THEN mv.plataforma_trip_1 ELSE 'Otros' END AS plataforma,
            CASE WHEN mv.canales_compra_trip_1 IN ('{_sql_list(top_canal)}') THEN mv.canales_compra_trip_1 ELSE 'Otros' END AS canal,
            COALESCE(mv.flg_app_90d_antes_trip1::VARCHAR, '-1') AS flg_app,
            COALESCE(mv.flg_uso_puntos::VARCHAR, '-1')           AS flg_puntos,
            CASE WHEN mv.n_transacciones_trip1=1 THEN '1' WHEN mv.n_transacciones_trip1=2 THEN '2' ELSE '3+' END AS n_trx,
            COALESCE(mv.tipo_viaje, 'Sin dato') AS tipo_viaje,
            CASE
                WHEN mv.productos_trip_2 IS NULL THEN 'Sin recompra'
                WHEN SPLIT_PART(mv.productos_trip_2, ' | ', 1) IN ('{_sql_list(top_productos_t2)}')
                    THEN SPLIT_PART(mv.productos_trip_2, ' | ', 1)
                ELSE 'Otros'
            END AS producto_t2,
            CASE
                WHEN mv.productos_trip_2 IS NULL THEN 'Sin recompra'
                WHEN t2.destino_t2_iata IN ('{_sql_list(top_destinos_t2)}') THEN t2.destino_t2_iata
                WHEN t2.destino_t2_iata IS NOT NULL THEN 'Otros'
                ELSE 'Sin recompra'
            END AS destino_t2,
            count(*) n,
            sum(CASE WHEN mv.eligible_18m THEN 1 ELSE 0 END) e18,
            sum(CASE WHEN mv.eligible_18m AND mv.rebuy_18m THEN 1 ELSE 0 END) r18,
            sum(CASE WHEN mv.eligible_12m THEN 1 ELSE 0 END) e12,
            sum(CASE WHEN mv.eligible_12m AND mv.rebuy_12m THEN 1 ELSE 0 END) r12,
            sum(CASE WHEN mv.eligible_6m  THEN 1 ELSE 0 END) e6,
            sum(CASE WHEN mv.eligible_6m  AND mv.rebuy_6m  THEN 1 ELSE 0 END) r6
        FROM mv
        LEFT JOIN t2_dest t2 ON mv.social_id = t2.social_id
        WHERE mv.n_transacciones_trip1 IS NOT NULL
        GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13
        HAVING count(*) >= 30
        ORDER BY 1,2,3,4,5,6,7,8,9,10,11,12,13
    """).fetchdf()
    # Serializar columna a columna para JSON compacto (tipo parquet column-store)
    out["explorador_cohortes"] = df_cube.to_dict(orient="list")
    # dims: destino_t1/t2 se guardan ORDENADOS POR VOLUMEN (no alfabético) para el dropdown
    cube_dest1_set = set(df_cube["destino_t1"].dropna().unique())
    cube_dest2_set = set(df_cube["destino_t2"].dropna().unique())
    out["explorador_cohortes_dims"] = {
        "pais":        sorted(df_cube["pais"].unique().tolist()),
        "producto_t1": sorted(df_cube["producto_t1"].unique().tolist()),
        "plataforma":  sorted(df_cube["plataforma"].unique().tolist()),
        "canal":       sorted(df_cube["canal"].unique().tolist()),
        "tipo_viaje":  sorted(df_cube["tipo_viaje"].unique().tolist()),
        "producto_t2": sorted(df_cube["producto_t2"].unique().tolist()),
        # order preserved: top by volume first, then 'Otros' at the end
        "destino_t1":  [c for c in top_destinos_t1 if c in cube_dest1_set] + (['Otros'] if 'Otros' in cube_dest1_set else []),
        "destino_t2":  [c for c in top_destinos_t2 if c in cube_dest2_set] + (['Otros'] if 'Otros' in cube_dest2_set else []) + (['Sin recompra'] if 'Sin recompra' in cube_dest2_set else []),
    }

    log("Contaminación de flg_app_90d_post_trip1 (leakage cuantificado)...")
    contam = con.execute("""
        SELECT count(*) n_rebuyers, sum(CASE WHEN flg_contaminado_90d_app THEN 1 ELSE 0 END) n_contaminados
        FROM mv WHERE rebuy_ever
    """).fetchdf().iloc[0]
    out["contaminacion_app_90d_post"] = {
        "n_rebuyers": int(contam.n_rebuyers), "n_contaminados": int(contam.n_contaminados),
        "pct_contaminados": float(contam.n_contaminados) / float(contam.n_rebuyers),
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

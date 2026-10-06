"""
FASE 2 - Vista de modelado a nivel usuario (leak-free) + targets multi-horizonte.

Logica de negocio de esta fase:
1. Agrega tx_level (SOLO nro_trip=1) a nivel social_id, sumando economics/eventos
   (aditivos, un usuario puede tener mas de una transaccion en su trip1) y tomando
   OR para flags. Esto es exactamente lo que el enunciado pide verificar: no sumar
   sobre filas de producto duplicadas, sino deduplicar por transaction_code primero
   (ya lo hace 01_build_base_tables.py) y despues agregar transacciones distintas.
2. Define targets de recompra a 6/12/24/36 meses usando aritmetica de mes
   calendario (no dias aproximados), consistente con la regla de 36 meses del
   pipeline SQL. Cada horizonte tiene su propio flag de elegibilidad (cohorte
   con tiempo de observacion completo) para no mezclar cohortes censuradas con
   maduras.
3. Marca flg_app_90d_post_trip1 como contaminado cuando el usuario recompro
   dentro de esos 90 dias (no se puede reconstruir la ventana exacta sin datos
   de visita individuales, que no estan en este export).
4. Deja fuera del dataset de modelado cualquier variable de Grupo C (ver
   variable_dictionary.py): eventos entre trips, variables de trip2, mismo
   producto, CRM historico.
5. Filtra la poblacion a cohortes con fecha_primer_trip >= FILTRO_FECHA_MINIMA
   (pedido de Matias Grussi, reunion 2026-09-21: excluir el periodo de pandemia
   2019-2021, que distorsiona la tasa de recompra y no representa el comportamiento
   actual). Este filtro reemplaza el analisis completo, no es un corte opcional.

Salidas:
  E:\\Soporte\\Reporting\\Rebuy\\_cache_v2\\modeling_view.parquet   (11.68M filas, 1 por usuario)
  2nd_rebuy\\modeling_view_sample_100k.csv                          (muestra para inspeccion)
  2nd_rebuy\\diccionario_variables.md                                (deliverable #6)
"""
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from variable_dictionary import as_markdown_table  # noqa: E402

CACHE_DIR = Path(r"E:\Soporte\Reporting\Rebuy\_cache_v2")
TX_PARQUET = CACHE_DIR / "tx_level.parquet"
USER_PARQUET = CACHE_DIR / "user_level.parquet"
MODELING_PARQUET = CACHE_DIR / "modeling_view.parquet"
PROJECT_DIR = Path(__file__).resolve().parent.parent
SAMPLE_CSV = PROJECT_DIR / "modeling_view_sample_100k.csv"
DICT_MD = PROJECT_DIR / "diccionario_variables.md"

HORIZONS = [6, 12, 18, 24, 36]  # 18m agregado a pedido de Matias (2026-09-21): estandar de retention para viajes
FILTRO_FECHA_MINIMA = "2022-01-01"  # pedido de Matias (2026-09-21): excluir cohortes 2019-2021 (periodo de pandemia)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    con = duckdb.connect()
    con.execute("PRAGMA disable_progress_bar")
    con.execute("PRAGMA memory_limit='20GB'")
    con.execute("PRAGMA threads=6")
    con.execute(f"PRAGMA temp_directory='{CACHE_DIR / 'duckdb_tmp'}'")

    log("Agregando tx_level (nro_trip=1) a nivel social_id...")
    con.execute(f"""
        CREATE OR REPLACE TABLE trip1_agg AS
        SELECT
            social_id,
            count(*) AS n_transacciones_trip1,
            min(reservation_datetime) AS trip1_primera_transaccion_dt,
            arg_min(pais, reservation_datetime) AS pais,
            arg_min(purchase_type, reservation_datetime) AS purchase_type,
            arg_min(product_type, reservation_datetime) AS product_type,
            arg_min(plataforma_compra, reservation_datetime) AS plataforma_compra_tx1,
            arg_min(canal_compra_agrupado, reservation_datetime) AS canal_compra_agrupado_tx1,
            arg_min(origen_trip, reservation_datetime) AS origen_trip,
            arg_min(destino_trip, reservation_datetime) AS destino_trip,
            arg_min(flight_class, reservation_datetime) AS flight_class,
            arg_min(tipo_viaje, reservation_datetime) AS tipo_viaje,
            arg_min(birth_year, reservation_datetime) AS birth_year,
            arg_min(edad_aprox_primer_trip, reservation_datetime) AS edad_aprox_primer_trip,
            arg_min(rango_edad_primer_trip, reservation_datetime) AS rango_edad_primer_trip,
            arg_min(income, reservation_datetime) AS income,
            arg_min(nationality, reservation_datetime) AS nationality,
            arg_min(pais_residencia, reservation_datetime) AS pais_residencia,
            arg_min(estado_residencia, reservation_datetime) AS estado_residencia,
            arg_min(ciudad_residencia, reservation_datetime) AS ciudad_residencia,
            arg_min(antiguedad_usuario_dias_al_trip1, reservation_datetime) AS antiguedad_usuario_dias_al_trip1,
            arg_min(geo_ultima_visita_ciudad, reservation_datetime) AS geo_ultima_visita_ciudad,
            arg_min(geo_ultima_visita_pais, reservation_datetime) AS geo_ultima_visita_pais,
            arg_min(geo_visita_frecuente_ciudad, reservation_datetime) AS geo_visita_frecuente_ciudad,
            arg_min(geo_visita_frecuente_pais, reservation_datetime) AS geo_visita_frecuente_pais,
            arg_min(trip_checkin, reservation_datetime) AS trip_checkin,
            arg_min(trip_checkout, reservation_datetime) AS trip_checkout,
            arg_min(dias_anticipacion_compra_checkin, reservation_datetime) AS dias_anticipacion_compra_checkin,
            arg_min(bucket_anticipacion_compra, reservation_datetime) AS bucket_anticipacion_compra,
            arg_min(duracion_viaje_dias, reservation_datetime) AS duracion_viaje_dias,
            arg_min(bucket_duracion_viaje, reservation_datetime) AS bucket_duracion_viaje,
            max(flg_uso_cupon) AS flg_uso_cupon,
            sum(puntos_usados) AS puntos_usados,
            max(flg_uso_puntos) AS flg_uso_puntos,
            arg_max(tier_al_momento_redencion, reservation_datetime) AS tier_al_momento_redencion,
            arg_max(metodos_pago, reservation_datetime) AS metodos_pago,
            max(flg_tarjeta_credito) AS flg_tarjeta_credito,
            max(flg_transferencia) AS flg_transferencia,
            max(flg_deposito_bancario) AS flg_deposito_bancario,
            max(flg_puntos_loyalty_pago) AS flg_puntos_loyalty_pago,
            max(flg_cupon_pago) AS flg_cupon_pago,
            max(flg_cash) AS flg_cash,
            max(flg_multi_instrumento_pago) AS flg_multi_instrumento_pago,
            max(flg_multi_tipo_pago) AS flg_multi_tipo_pago,
            sum(gross_bookings_usd) AS gross_bookings_usd,
            sum(cost_usd) AS cost_usd,
            sum(margin_variable_usd) AS margin_variable_usd,
            sum(net_revenues_usd) AS net_revenues_usd,
            sum(npv_usd) AS npv_usd,
            sum(fee_net_usd) AS fee_net_usd,
            sum(gb_total_payments) AS gb_total_payments,
            max(flg_customer_service) AS flg_customer_service,
            sum(cantidad_interacciones_cs) AS cantidad_interacciones_cs,
            max(flg_cs_satisfecho) AS flg_cs_satisfecho,
            max(flg_cs_insatisfecho) AS flg_cs_insatisfecho,
            max(flg_cs_resuelto) AS flg_cs_resuelto,
            max(flg_cs_no_resuelto) AS flg_cs_no_resuelto,
            avg(avg_agent_empathy_cs) AS avg_agent_empathy_cs,
            min(first_click_datetime) AS first_click_datetime,
            arg_min(first_click_event_type, first_click_datetime) AS first_click_event_type,
            max(last_click_datetime) AS last_click_datetime,
            arg_max(last_click_event_type, last_click_datetime) AS last_click_event_type,
            sum(eventos_directo) AS eventos_directo,
            sum(eventos_sem_seo_kwbrand) AS eventos_sem_seo_kwbrand,
            sum(eventos_metabuscadores) AS eventos_metabuscadores,
            sum(eventos_crm) AS eventos_crm,
            sum(eventos_otros) AS eventos_otros,
            sum(eventos_path_total) AS eventos_path_total
        FROM read_parquet('{TX_PARQUET}')
        WHERE nro_trip = 1
        GROUP BY social_id
    """)
    n1 = con.execute("SELECT count(*) FROM trip1_agg").fetchone()[0]
    log(f"trip1_agg: {n1:,} usuarios")

    log("Uniendo con user_level y calculando targets multi-horizonte...")
    max_date = con.execute(f"SELECT max(fecha_primer_trip) FROM read_parquet('{USER_PARQUET}')").fetchone()[0]
    log(f"Fecha maxima de primer trip observada en los datos: {max_date}")

    horizon_cols = []
    for h in HORIZONS:
        horizon_cols.append(f"""
            (u.fecha_primer_trip <= DATE '{max_date}' - INTERVAL ({h}) MONTH) AS eligible_{h}m,
            (u.fecha_segundo_trip IS NOT NULL
                AND u.fecha_segundo_trip <= u.fecha_primer_trip + INTERVAL ({h}) MONTH) AS rebuy_{h}m
        """)
    horizon_sql = ",".join(horizon_cols)

    con.execute(f"""
        CREATE OR REPLACE TABLE modeling_view AS
        SELECT
            u.social_id,
            u.tipo_usuario,
            u.fecha_primer_trip,
            u.fecha_segundo_trip,
            (u.fecha_segundo_trip IS NOT NULL) AS rebuy_ever,
            CASE WHEN u.fecha_segundo_trip IS NOT NULL
                 THEN date_diff('day', u.fecha_primer_trip, u.fecha_segundo_trip) END AS dias_a_recompra,
            date_diff('day', u.fecha_primer_trip, DATE '{max_date}') AS dias_observados_desde_trip1,
            strftime(u.fecha_primer_trip, '%Y') AS cohort_year,
            strftime(u.fecha_primer_trip, '%Y-%m') AS cohort_month,
            {horizon_sql},
            -- ---- GRUPO A: features trip1, seguras para modelo ----
            t.pais,
            t.purchase_type,
            t.product_type,
            COALESCE(u.plataforma_trip_1, t.plataforma_compra_tx1) AS plataforma_trip_1,
            COALESCE(u.canales_compra_trip_1, t.canal_compra_agrupado_tx1) AS canales_compra_trip_1,
            (COALESCE(u.plataforma_trip_1, '') LIKE '%|%') AS flg_multi_plataforma_trip1,
            t.origen_trip, t.destino_trip,
            t.flight_class,
            (t.flight_class IS NOT NULL) AS tiene_vuelo,
            t.tipo_viaje, t.birth_year, t.edad_aprox_primer_trip, t.rango_edad_primer_trip,
            t.income, t.nationality, t.pais_residencia, t.estado_residencia, t.ciudad_residencia,
            t.antiguedad_usuario_dias_al_trip1,
            t.geo_ultima_visita_ciudad, t.geo_ultima_visita_pais,
            t.geo_visita_frecuente_ciudad, t.geo_visita_frecuente_pais,
            t.trip_checkin, t.trip_checkout,
            t.dias_anticipacion_compra_checkin, t.bucket_anticipacion_compra,
            t.duracion_viaje_dias, t.bucket_duracion_viaje,
            t.flg_uso_cupon,
            t.flg_uso_puntos, t.puntos_usados, t.tier_al_momento_redencion,
            t.metodos_pago, t.flg_tarjeta_credito, t.flg_transferencia, t.flg_deposito_bancario,
            t.flg_puntos_loyalty_pago, t.flg_cupon_pago, t.flg_cash,
            t.flg_multi_instrumento_pago, t.flg_multi_tipo_pago,
            t.n_transacciones_trip1,
            t.gross_bookings_usd, t.cost_usd, t.margin_variable_usd, t.net_revenues_usd,
            t.npv_usd, t.fee_net_usd, t.gb_total_payments,
            (u.fecha_primer_trip >= DATE '2020-01-01') AS cohorte_con_margin_valido,
            t.eventos_directo, t.eventos_sem_seo_kwbrand, t.eventos_metabuscadores,
            t.eventos_crm, t.eventos_otros, t.eventos_path_total,
            (u.fecha_primer_trip >= DATE '2021-01-01') AS cohorte_con_path_medios_valido,
            t.first_click_datetime, t.last_click_datetime, t.first_click_event_type, t.last_click_event_type,
            u.flg_app_90d_antes_trip1, u.visitas_app_90d_antes_trip1,
            u.ultima_visita_app_antes_trip1,
            CASE WHEN u.flg_app_90d_antes_trip1 = 1
                 THEN date_diff('day', CAST(u.ultima_visita_app_antes_trip1 AS DATE), u.fecha_primer_trip) END
                 AS dias_desde_ultima_visita_app_antes_trip1,
            -- ---- GRUPO B: post trip1 con contaminacion marcada ----
            u.flg_app_90d_post_trip1, u.visitas_app_90d_post_trip1,
            (u.fecha_segundo_trip IS NOT NULL
                AND date_diff('day', u.fecha_primer_trip, u.fecha_segundo_trip) <= 90) AS flg_contaminado_90d_app,
            CASE WHEN NOT (u.fecha_segundo_trip IS NOT NULL
                AND date_diff('day', u.fecha_primer_trip, u.fecha_segundo_trip) <= 90)
                 THEN u.flg_app_90d_post_trip1 END AS flg_app_90d_post_trip1_leakfree,
            CASE WHEN NOT (u.fecha_segundo_trip IS NOT NULL
                AND date_diff('day', u.fecha_primer_trip, u.fecha_segundo_trip) <= 90)
                 THEN u.visitas_app_90d_post_trip1 END AS visitas_app_90d_post_trip1_leakfree,
            -- ---- GRUPO C: leakage, SOLO para descriptivos "entre recompradores" (nunca como feature) ----
            u.cantidad_visitas_entre_trips, u.cantidad_searches_entre_trips,
            u.flg_app_entre_trips, u.visitas_app_entre_trips, u.ultima_visita_app_antes_trip2,
            u.plataforma_trip_2, u.canales_compra_trip_2,
            u.productos_trip_1, u.productos_trip_2, u.flg_mismo_producto_trip_1_2,
            -- Customer Service (Grupo D, descriptivo): agregado de trip1, sin timestamp de
            -- la interaccion -> no se puede fijar temporalidad respecto de trip2.
            t.flg_customer_service, t.cantidad_interacciones_cs, t.flg_cs_satisfecho,
            t.flg_cs_insatisfecho, t.flg_cs_resuelto, t.flg_cs_no_resuelto, t.avg_agent_empathy_cs
        FROM read_parquet('{USER_PARQUET}') u
        LEFT JOIN trip1_agg t ON u.social_id = t.social_id
        WHERE u.fecha_primer_trip >= DATE '{FILTRO_FECHA_MINIMA}'
    """)

    n_final = con.execute("SELECT count(*) FROM modeling_view").fetchone()[0]
    log(f"modeling_view: {n_final:,} usuarios (filtrado a cohortes desde {FILTRO_FECHA_MINIMA}, pedido de Matias 2026-09-21 para excluir el periodo de pandemia)")

    con.execute(f"COPY modeling_view TO '{MODELING_PARQUET}' (FORMAT PARQUET)")
    log(f"Guardado {MODELING_PARQUET}")

    log("Exportando muestra CSV de 100k filas...")
    con.execute(f"""
        COPY (SELECT * FROM modeling_view USING SAMPLE 100000 (reservoir, 42))
        TO '{SAMPLE_CSV}' (FORMAT CSV, HEADER)
    """)
    log(f"Guardado {SAMPLE_CSV}")

    DICT_MD.write_text(
        "# Diccionario de variables - REBUY v2\n\n"
        "Clasificacion por temporalidad y riesgo de leakage. Grupo A = seguro para prediccion "
        "(disponible al momento de trip1). Grupo B = post-trip1 con ventana controlable. "
        "Grupo C = leakage directo del target, nunca usar como feature. Grupo D = descriptivo, "
        "cobertura/temporalidad no resuelta.\n\n" + as_markdown_table() + "\n",
        encoding="utf-8",
    )
    log(f"Guardado {DICT_MD}")


if __name__ == "__main__":
    main()

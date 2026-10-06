"""
FASE 1 - Tablas base deduplicadas desde tmp.rebuy_final (export CSV mensual).

Por que existe este script:
La tabla final tiene grano social_id + nro_trip + trip_id + transaction_code + producto
(confirmado en el PDF y verificado empiricamente: 17.6M transaction_code distintos,
avg 1.23 filas por transaccion, max 12). Los campos de economics/loyalty/payments/CS/
first-last-click viven a nivel transaction_code, y los de App/actividad-entre-trips
viven a nivel social_id. Sumar o promediar directamente sobre las filas crudas los
multiplicaria por la cantidad de filas de producto. Por eso el primer paso SIEMPRE
es deduplicar a la grana correcta antes de agregar nada.

Verificacion hecha antes de escribir esto (ver auditoria en la conversacion):
- 0 transacciones con valores inconsistentes de gb/cupon/puntos/cs/pago entre sus
  filas duplicadas -> es seguro tomar cualquiera (ANY_VALUE / first) por transaction_code.
- 0 usuarios con valores inconsistentes de flags de App o fechas entre sus filas
  duplicadas -> es seguro tomar cualquiera por social_id.

Salidas (parquet, fuera del webroot):
  E:\\Soporte\\Reporting\\Rebuy\\_cache_v2\\tx_level.parquet    (1 fila por transaction_code)
  E:\\Soporte\\Reporting\\Rebuy\\_cache_v2\\user_level.parquet  (1 fila por social_id)
"""
import time
from pathlib import Path

import duckdb

RAW_GLOB = r"E:\Soporte\Reporting\Rebuy\historico\rebuy_final_*.csv"
CACHE_DIR = Path(r"E:\Soporte\Reporting\Rebuy\_cache_v2")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
TX_PARQUET = CACHE_DIR / "tx_level.parquet"
USER_PARQUET = CACHE_DIR / "user_level.parquet"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main(force=False):
    if TX_PARQUET.exists() and USER_PARQUET.exists() and not force:
        log("Cache ya existe (tx_level.parquet y user_level.parquet) - uso --rebuild para forzar.")
        return

    con = duckdb.connect()
    con.execute("PRAGMA disable_progress_bar")
    con.execute("PRAGMA memory_limit='20GB'")
    con.execute("PRAGMA threads=6")
    con.execute(f"PRAGMA temp_directory='{CACHE_DIR / 'duckdb_tmp'}'")
    con.execute(f"""
        CREATE OR REPLACE VIEW raw AS
        SELECT * FROM read_csv(
            '{RAW_GLOB}',
            union_by_name=true,
            quote='"',
            escape='"',
            ignore_errors=true
        )
    """)

    # -----------------------------------------------------------------
    # tx_level: 1 fila por transaction_code, con TODOS los campos que
    # viven a ese nivel (economics, loyalty, payments, CS, cupon,
    # first/last click, path de medios, flight_class, producto/pais/
    # plataforma/canal DE ESA transaccion puntual).
    # -----------------------------------------------------------------
    log("Construyendo tx_level.parquet (1 fila por transaction_code)...")
    con.execute(f"""
        COPY (
            SELECT
                transaction_code,
                arg_min(social_id, reservation_datetime) AS social_id,
                arg_min(nro_trip, reservation_datetime) AS nro_trip,
                arg_min(trip_id, reservation_datetime) AS trip_id,
                min(reservation_date) AS reservation_date,
                min(reservation_datetime) AS reservation_datetime,
                arg_min(purchase_type, reservation_datetime) AS purchase_type,
                arg_min(pais, reservation_datetime) AS pais,
                arg_min(plataforma_compra, reservation_datetime) AS plataforma_compra,
                arg_min(canal_compra_agrupado, reservation_datetime) AS canal_compra_agrupado,
                arg_min(origen_trip, reservation_datetime) AS origen_trip,
                arg_min(destino_trip, reservation_datetime) AS destino_trip,
                arg_min(flight_class, reservation_datetime) AS flight_class,
                -- producto principal de la transaccion (representativo). La composicion completa
                -- del basket ya esta resuelta a nivel usuario en productos_trip_1/2 (user_level).
                arg_min(product_type, reservation_datetime) AS product_type,
                count(DISTINCT product_type) AS n_product_types,
                -- ---- Variables nuevas 2026-09-21 (perfil de usuario + caracteristicas del viaje) ----
                -- Ver variable_dictionary.py: son snapshots por fila, no fijos por social_id;
                -- se toma siempre la transaccion mas temprana como representativa de trip1.
                arg_min(tipo_viaje, reservation_datetime) AS tipo_viaje,
                arg_min(TRY_CAST(birth_year AS INTEGER), reservation_datetime) AS birth_year,
                arg_min(TRY_CAST(edad_aprox_primer_trip AS INTEGER), reservation_datetime) AS edad_aprox_primer_trip,
                arg_min(rango_edad_primer_trip, reservation_datetime) AS rango_edad_primer_trip,
                arg_min(income, reservation_datetime) AS income,
                arg_min(nationality, reservation_datetime) AS nationality,
                arg_min(pais_residencia, reservation_datetime) AS pais_residencia,
                arg_min(estado_residencia, reservation_datetime) AS estado_residencia,
                arg_min(ciudad_residencia, reservation_datetime) AS ciudad_residencia,
                arg_min(TRY_CAST(antiguedad_usuario_dias_al_trip1 AS INTEGER), reservation_datetime) AS antiguedad_usuario_dias_al_trip1,
                arg_min(geo_ultima_visita_ciudad, reservation_datetime) AS geo_ultima_visita_ciudad,
                arg_min(geo_ultima_visita_pais, reservation_datetime) AS geo_ultima_visita_pais,
                arg_min(geo_visita_frecuente_ciudad, reservation_datetime) AS geo_visita_frecuente_ciudad,
                arg_min(geo_visita_frecuente_pais, reservation_datetime) AS geo_visita_frecuente_pais,
                arg_min(TRY_CAST(trip_checkin AS DATE), reservation_datetime) AS trip_checkin,
                arg_min(TRY_CAST(trip_checkout AS DATE), reservation_datetime) AS trip_checkout,
                -- dias_anticipacion_compra_checkin SI varia entre transacciones de un mismo trip1
                -- (~10% de los casos): se usa la de la transaccion mas temprana (reserva principal).
                arg_min(TRY_CAST(dias_anticipacion_compra_checkin AS INTEGER), reservation_datetime) AS dias_anticipacion_compra_checkin,
                arg_min(bucket_anticipacion_compra, reservation_datetime) AS bucket_anticipacion_compra,
                arg_min(TRY_CAST(duracion_viaje_dias AS INTEGER), reservation_datetime) AS duracion_viaje_dias,
                arg_min(bucket_duracion_viaje, reservation_datetime) AS bucket_duracion_viaje,
                -- cupon / loyalty / CS / click / path: constantes por transaction_code (verificado)
                max(TRY_CAST(flg_uso_cupon AS INTEGER)) AS flg_uso_cupon,
                max(TRY_CAST(puntos_usados AS DOUBLE)) AS puntos_usados,
                max(TRY_CAST(flg_uso_puntos AS INTEGER)) AS flg_uso_puntos,
                arg_max(tier_redencion_raw, reservation_datetime) AS tier_redencion_raw,
                arg_max(tier_al_momento_redencion, reservation_datetime) AS tier_al_momento_redencion,
                arg_max(metodos_pago, reservation_datetime) AS metodos_pago,
                max(TRY_CAST(cantidad_pagos AS INTEGER)) AS cantidad_pagos,
                max(TRY_CAST(cantidad_instrumentos_pago AS INTEGER)) AS cantidad_instrumentos_pago,
                max(TRY_CAST(cantidad_tipos_pago AS INTEGER)) AS cantidad_tipos_pago,
                max(TRY_CAST(flg_multi_instrumento_pago AS INTEGER)) AS flg_multi_instrumento_pago,
                max(TRY_CAST(flg_multi_tipo_pago AS INTEGER)) AS flg_multi_tipo_pago,
                max(TRY_CAST(gb_total_payments AS DOUBLE)) AS gb_total_payments,
                max(TRY_CAST(pct_gb_tarjeta_credito AS DOUBLE)) AS pct_gb_tarjeta_credito,
                max(TRY_CAST(pct_gb_transferencia AS DOUBLE)) AS pct_gb_transferencia,
                max(TRY_CAST(pct_gb_deposito_bancario AS DOUBLE)) AS pct_gb_deposito_bancario,
                max(TRY_CAST(pct_gb_puntos_loyalty AS DOUBLE)) AS pct_gb_puntos_loyalty,
                max(TRY_CAST(pct_gb_cupon AS DOUBLE)) AS pct_gb_cupon,
                max(TRY_CAST(pct_gb_cash AS DOUBLE)) AS pct_gb_cash,
                max(TRY_CAST(flg_tarjeta_credito AS INTEGER)) AS flg_tarjeta_credito,
                max(TRY_CAST(flg_transferencia AS INTEGER)) AS flg_transferencia,
                max(TRY_CAST(flg_deposito_bancario AS INTEGER)) AS flg_deposito_bancario,
                max(TRY_CAST(flg_puntos_loyalty_pago AS INTEGER)) AS flg_puntos_loyalty_pago,
                max(TRY_CAST(flg_cupon_pago AS INTEGER)) AS flg_cupon_pago,
                max(TRY_CAST(flg_cash AS INTEGER)) AS flg_cash,
                max(TRY_CAST(flg_customer_service AS INTEGER)) AS flg_customer_service,
                max(TRY_CAST(cantidad_interacciones_cs AS INTEGER)) AS cantidad_interacciones_cs,
                max(TRY_CAST(cantidad_conversaciones_cs AS INTEGER)) AS cantidad_conversaciones_cs,
                max(TRY_CAST(flg_cs_satisfecho AS INTEGER)) AS flg_cs_satisfecho,
                max(TRY_CAST(flg_cs_insatisfecho AS INTEGER)) AS flg_cs_insatisfecho,
                max(TRY_CAST(flg_cs_resuelto AS INTEGER)) AS flg_cs_resuelto,
                max(TRY_CAST(flg_cs_no_resuelto AS INTEGER)) AS flg_cs_no_resuelto,
                max(TRY_CAST(avg_agent_empathy_cs AS DOUBLE)) AS avg_agent_empathy_cs,
                min(TRY_CAST(first_click_datetime AS TIMESTAMP)) AS first_click_datetime,
                arg_min(first_click_event_type, reservation_datetime) AS first_click_event_type,
                max(TRY_CAST(last_click_datetime AS TIMESTAMP)) AS last_click_datetime,
                arg_max(last_click_event_type, reservation_datetime) AS last_click_event_type,
                max(TRY_CAST(gross_bookings_usd AS DOUBLE)) AS gross_bookings_usd,
                max(TRY_CAST(cost_usd AS DOUBLE)) AS cost_usd,
                max(TRY_CAST(margin_variable_without_mkt_net_usd AS DOUBLE)) AS margin_variable_usd,
                max(TRY_CAST(net_revenues_usd AS DOUBLE)) AS net_revenues_usd,
                max(TRY_CAST(npv_without_mkt_net_usd AS DOUBLE)) AS npv_usd,
                max(TRY_CAST(fee_net_usd AS DOUBLE)) AS fee_net_usd,
                max(TRY_CAST(eventos_directo AS INTEGER)) AS eventos_directo,
                max(TRY_CAST(eventos_sem_seo_kwbrand AS INTEGER)) AS eventos_sem_seo_kwbrand,
                max(TRY_CAST(eventos_metabuscadores AS INTEGER)) AS eventos_metabuscadores,
                max(TRY_CAST(eventos_crm AS INTEGER)) AS eventos_crm,
                max(TRY_CAST(eventos_otros AS INTEGER)) AS eventos_otros,
                max(TRY_CAST(eventos_path_total AS INTEGER)) AS eventos_path_total
            FROM raw
            WHERE transaction_code IS NOT NULL
            GROUP BY transaction_code
        ) TO '{TX_PARQUET}' (FORMAT PARQUET)
    """)
    n_tx = con.execute(f"SELECT count(*) FROM read_parquet('{TX_PARQUET}')").fetchone()[0]
    log(f"tx_level.parquet listo: {n_tx:,} transacciones")

    # -----------------------------------------------------------------
    # user_level: 1 fila por social_id, campos que viven a ese nivel
    # (App, actividad entre trips, fechas, tipo_usuario, plataforma/canal
    # /productos resumidos de trip1 y trip2, flag mismo producto).
    # -----------------------------------------------------------------
    log("Construyendo user_level.parquet (1 fila por social_id)...")
    con.execute(f"""
        COPY (
            SELECT
                social_id,
                arg_min(tipo_usuario, reservation_datetime) AS tipo_usuario,
                min(CAST(fecha_primer_trip AS DATE)) AS fecha_primer_trip,
                min(CAST(fecha_segundo_trip AS DATE)) AS fecha_segundo_trip,
                max(TRY_CAST(flg_app_90d_antes_trip1 AS INTEGER)) AS flg_app_90d_antes_trip1,
                max(TRY_CAST(visitas_app_90d_antes_trip1 AS INTEGER)) AS visitas_app_90d_antes_trip1,
                max(TRY_CAST(flg_app_entre_trips AS INTEGER)) AS flg_app_entre_trips,
                max(TRY_CAST(visitas_app_entre_trips AS INTEGER)) AS visitas_app_entre_trips,
                max(TRY_CAST(flg_app_90d_post_trip1 AS INTEGER)) AS flg_app_90d_post_trip1,
                max(TRY_CAST(visitas_app_90d_post_trip1 AS INTEGER)) AS visitas_app_90d_post_trip1,
                max(TRY_CAST(ultima_visita_app_antes_trip1 AS TIMESTAMP)) AS ultima_visita_app_antes_trip1,
                max(TRY_CAST(ultima_visita_app_antes_trip2 AS TIMESTAMP)) AS ultima_visita_app_antes_trip2,
                max(TRY_CAST(cantidad_visitas_entre_trips AS INTEGER)) AS cantidad_visitas_entre_trips,
                max(TRY_CAST(cantidad_searches_entre_trips AS INTEGER)) AS cantidad_searches_entre_trips,
                arg_min(plataforma_trip_1, reservation_datetime) AS plataforma_trip_1,
                arg_min(plataforma_trip_2, reservation_datetime) AS plataforma_trip_2,
                arg_min(canales_compra_trip_1, reservation_datetime) AS canales_compra_trip_1,
                arg_min(canales_compra_trip_2, reservation_datetime) AS canales_compra_trip_2,
                arg_min(productos_trip_1, reservation_datetime) AS productos_trip_1,
                arg_min(productos_trip_2, reservation_datetime) AS productos_trip_2,
                max(TRY_CAST(flg_mismo_producto_trip_1_2 AS INTEGER)) AS flg_mismo_producto_trip_1_2
            FROM raw
            WHERE social_id IS NOT NULL
            GROUP BY social_id
        ) TO '{USER_PARQUET}' (FORMAT PARQUET)
    """)
    n_users = con.execute(f"SELECT count(*) FROM read_parquet('{USER_PARQUET}')").fetchone()[0]
    log(f"user_level.parquet listo: {n_users:,} usuarios")


if __name__ == "__main__":
    import sys
    main(force="--rebuild" in sys.argv)

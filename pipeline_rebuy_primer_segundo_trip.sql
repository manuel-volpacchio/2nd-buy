-- ============================================================
-- PIPELINE REBUY - PRIMER Y SEGUNDO TRIP
-- Despegar | B2C
--
-- Incluye:
--   1. transacciones Despegar B2C confirmadas
--   2. trips confirmados
--   3. primer y segundo trip + ventana de 36 meses
--   4. detalle de transacciones/productos
--   5. rango global necesario de visitas
--   6. visitas y searches entre trip 1 y trip 2
--   7. plataforma y canal de compra
--   8. productos trip 1 vs trip 2
--   9. transacciones objetivo
--  10. path de medios
--  11. flight class
--  12. uso de cupón
--  13. economics
--  14. first click / last click
--  15. puntos y tier al momento de redención
--  16. customer service / NPS inferido
--  17. visitas App
--  18. comportamiento App
--  19. métodos de pago
--  20. perfil usuario: edad, income, residencia y geolocalización
--  21. tabla final consolidada
--  22. controles finales
--
-- Criterios App:
--   - App = main_channel IN ('iphone-app', 'android-app')
--   - ventana previa a trip 1 = 90 días
--   - ventana posterior a trip 1 = 90 días
--   - entre trips = desde trip 1 hasta trip 2, solo usuarios con segundo trip
--
-- Nota:
--   - analytics.mkt_users_fact_visits exige filtro de partición visit_date.
--   - CRM histórico/interacciones queda fuera por ahora hasta cerrar cobertura.
--   - mkt_users_dim_users se toma en su último estado disponible por social_id.
--   - edad al primer trip se aproxima como YEAR(fecha_primer_trip) - birth_year.
--   - geo de última/frecuente visita y última transacción son estado actual/último conocido, no histórico al trip 1.
-- ============================================================

-- ============================================================
-- 1. TRANSACCIONES DESPEGAR B2C
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_trx_b2c_despegar;

CREATE TABLE tmp.rebuy_trx_b2c_despegar AS
SELECT
    CAST(transaction_code AS VARCHAR) AS transaction_code,
    CAST(social_id AS VARCHAR) AS social_id,
    MAX(reservation_date) AS reservation_date,
    MAX_BY(reservation_datetime, reservation_datetime) AS reservation_datetime,
    MAX_BY(platform, reservation_datetime) AS platform,
    MAX_BY(parent_channel, reservation_datetime) AS parent_channel,
    MAX_BY(trip_type, reservation_datetime) AS trip_type
FROM analytics.mkt_users_fact_transactions
WHERE reservation_year_month IS NOT NULL
  AND brand = 'Despegar'
  AND line_of_business = 'B2C'
  AND transaction_status = 'Confirmado'
  AND social_id IS NOT NULL
  AND transaction_code IS NOT NULL
GROUP BY
    CAST(transaction_code AS VARCHAR),
    CAST(social_id AS VARCHAR);

-- ============================================================
-- 2. TRIPS CONFIRMADOS DE ESOS USUARIOS
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_trips_base;

CREATE TABLE tmp.rebuy_trips_base AS
SELECT
    t.social_id,
    t.trip_id,
    MIN(t.reservation_datetime) AS fecha_trip
FROM lake.clientes_trips_fact t
INNER JOIN tmp.rebuy_trx_b2c_despegar f
    ON t.social_id = f.social_id
   AND CAST(t.transaction_code AS VARCHAR) = f.transaction_code
WHERE t.reservation_year_month IS NOT NULL
  AND t.trip_status = 'Confirmado'
  AND t.transaction_status = 'Confirmado'
  AND t.social_id IS NOT NULL
  AND t.trip_id IS NOT NULL
  AND t.brand = 'Despegar'
GROUP BY
    t.social_id,
    t.trip_id;

-- ============================================================
-- 3. PRIMER Y SEGUNDO TRIP + FILTRO 36 MESES
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_usuarios_validos;

CREATE TABLE tmp.rebuy_usuarios_validos AS
WITH trips_ordenados AS (
    SELECT
        social_id,
        trip_id,
        fecha_trip,
        ROW_NUMBER() OVER (
            PARTITION BY social_id
            ORDER BY fecha_trip ASC, trip_id ASC
        ) AS orden_trip
    FROM tmp.rebuy_trips_base
),
usuarios AS (
    SELECT
        social_id,
        MAX(CASE WHEN orden_trip = 1 THEN trip_id END) AS trip_id_1,
        MAX(CASE WHEN orden_trip = 1 THEN fecha_trip END) AS fecha_primer_trip,
        MAX(CASE WHEN orden_trip = 2 THEN trip_id END) AS trip_id_2,
        MAX(CASE WHEN orden_trip = 2 THEN fecha_trip END) AS fecha_segundo_trip
    FROM trips_ordenados
    WHERE orden_trip <= 2
    GROUP BY social_id
)
SELECT
    social_id,
    trip_id_1,
    fecha_primer_trip,
    trip_id_2,
    fecha_segundo_trip
FROM usuarios
WHERE fecha_segundo_trip IS NULL
   OR fecha_segundo_trip <= DATE_ADD('month', 36, fecha_primer_trip);

-- ============================================================
-- 4. DETALLE TRANSACCION / PRODUCTO DE TRIP 1 Y TRIP 2
-- + TIPO DE VIAJE, CHECKIN/CHECKOUT, ANTICIPACION Y DURACION
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_detalle;

CREATE TABLE tmp.rebuy_detalle AS
SELECT DISTINCT
    u.social_id,
    CASE
        WHEN t.trip_id = u.trip_id_1 THEN 1
        WHEN t.trip_id = u.trip_id_2 THEN 2
    END AS nro_trip,
    t.trip_id,
    CAST(t.transaction_code AS VARCHAR) AS transaction_code,
    t.purchase_type,
    t.product_type,
    t.country_code AS pais,
    f.trip_type AS tipo_viaje,
    f.platform AS plataforma_compra,
    f.parent_channel AS canal_compra_agrupado,
    t.first_origin_id AS origen_trip,
    t.first_destination_id AS destino_trip,
    t.reservation_date,
    t.reservation_datetime,
    CAST(t.trip_checkin AS TIMESTAMP) AS trip_checkin,
    CAST(t.trip_checkout AS TIMESTAMP) AS trip_checkout,
    CASE
        WHEN t.reservation_datetime IS NOT NULL
         AND t.trip_checkin IS NOT NULL
        THEN DATE_DIFF(
            'day',
            CAST(t.reservation_datetime AS DATE),
            CAST(t.trip_checkin AS DATE)
        )
    END AS dias_anticipacion_compra_checkin,
    CASE
        WHEN t.trip_checkin IS NOT NULL
         AND t.trip_checkout IS NOT NULL
        THEN DATE_DIFF(
            'day',
            CAST(t.trip_checkin AS DATE),
            CAST(t.trip_checkout AS DATE)
        )
    END AS duracion_viaje_dias,
    CAST(u.fecha_primer_trip AS DATE) AS fecha_primer_trip,
    CAST(u.fecha_segundo_trip AS DATE) AS fecha_segundo_trip,
    CASE
        WHEN u.fecha_segundo_trip IS NULL THEN '1 trip'
        ELSE '2 o mas trips'
    END AS tipo_usuario
FROM tmp.rebuy_usuarios_validos u
INNER JOIN lake.clientes_trips_fact t
    ON u.social_id = t.social_id
   AND (
        t.trip_id = u.trip_id_1
        OR t.trip_id = u.trip_id_2
   )
INNER JOIN tmp.rebuy_trx_b2c_despegar f
    ON t.social_id = f.social_id
   AND CAST(t.transaction_code AS VARCHAR) = f.transaction_code
WHERE t.reservation_year_month IS NOT NULL
  AND t.trip_status = 'Confirmado'
  AND t.transaction_status = 'Confirmado'
  AND t.brand = 'Despegar';

-- ============================================================
-- 5. RANGO GLOBAL NECESARIO DE VISITAS
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_rango_visitas;

CREATE TABLE tmp.rebuy_rango_visitas AS
SELECT
    MIN(CAST(fecha_primer_trip AS DATE)) AS fecha_min,
    MAX(CAST(fecha_segundo_trip AS DATE)) AS fecha_max
FROM tmp.rebuy_usuarios_validos
WHERE fecha_segundo_trip IS NOT NULL;

-- ============================================================
-- 6. VISITAS Y SEARCHES ENTRE TRIP 1 Y TRIP 2
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_actividad_entre_trips;

CREATE TABLE tmp.rebuy_actividad_entre_trips AS
SELECT
    u.social_id,
    COUNT(DISTINCT v.visit_id) AS cantidad_visitas_entre_trips,
    SUM(COALESCE(v.count_search, 0)) AS cantidad_searches_entre_trips
FROM analytics.mkt_users_fact_visits v
INNER JOIN tmp.rebuy_usuarios_validos u
    ON CAST(v.social_id AS VARCHAR) = u.social_id
   AND CAST(v.start_visit AS TIMESTAMP) > CAST(u.fecha_primer_trip AS TIMESTAMP)
   AND CAST(v.start_visit AS TIMESTAMP) < CAST(u.fecha_segundo_trip AS TIMESTAMP)
CROSS JOIN tmp.rebuy_rango_visitas r
WHERE u.fecha_segundo_trip IS NOT NULL
  AND v.visit_date >= CAST(DATE_ADD('year', -10, CURRENT_DATE) AS VARCHAR)
  AND v.visit_date <= CAST(CURRENT_DATE AS VARCHAR)
  AND v.visit_date >= CAST(r.fecha_min AS VARCHAR)
  AND v.visit_date <= CAST(r.fecha_max AS VARCHAR)
  AND UPPER(TRIM(v.company)) = 'DESPEGAR'
  AND v.social_id IS NOT NULL
  AND v.visit_id IS NOT NULL
GROUP BY
    u.social_id;

-- ============================================================
-- 7. PLATAFORMAS Y CANALES DE COMPRA TRIP 1 Y TRIP 2
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_compra_por_trip;

CREATE TABLE tmp.rebuy_compra_por_trip AS
SELECT
    social_id,
    ARRAY_JOIN(
        ARRAY_AGG(DISTINCT plataforma_compra)
        FILTER (WHERE nro_trip = 1 AND plataforma_compra IS NOT NULL),
        ' | '
    ) AS plataforma_trip_1,
    ARRAY_JOIN(
        ARRAY_AGG(DISTINCT plataforma_compra)
        FILTER (WHERE nro_trip = 2 AND plataforma_compra IS NOT NULL),
        ' | '
    ) AS plataforma_trip_2,
    ARRAY_JOIN(
        ARRAY_AGG(DISTINCT canal_compra_agrupado)
        FILTER (WHERE nro_trip = 1 AND canal_compra_agrupado IS NOT NULL),
        ' | '
    ) AS canales_compra_trip_1,
    ARRAY_JOIN(
        ARRAY_AGG(DISTINCT canal_compra_agrupado)
        FILTER (WHERE nro_trip = 2 AND canal_compra_agrupado IS NOT NULL),
        ' | '
    ) AS canales_compra_trip_2
FROM tmp.rebuy_detalle
GROUP BY social_id;

-- ============================================================
-- 8. PRODUCTOS TRIP 1 VS TRIP 2
-- + FLAG MISMO PRODUCTO
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_productos_social;

CREATE TABLE tmp.rebuy_productos_social AS
WITH productos AS (
    SELECT DISTINCT
        social_id,
        nro_trip,
        product_type
    FROM tmp.rebuy_detalle
    WHERE product_type IS NOT NULL
),
listas AS (
    SELECT
        social_id,
        ARRAY_JOIN(
            ARRAY_AGG(DISTINCT product_type) FILTER (WHERE nro_trip = 1),
            ' | '
        ) AS productos_trip_1,
        ARRAY_JOIN(
            ARRAY_AGG(DISTINCT product_type) FILTER (WHERE nro_trip = 2),
            ' | '
        ) AS productos_trip_2
    FROM productos
    GROUP BY social_id
),
matches AS (
    SELECT DISTINCT
        a.social_id
    FROM productos a
    INNER JOIN productos b
        ON a.social_id = b.social_id
       AND a.product_type = b.product_type
       AND a.nro_trip = 1
       AND b.nro_trip = 2
)
SELECT
    l.social_id,
    l.productos_trip_1,
    l.productos_trip_2,
    CASE
        WHEN m.social_id IS NOT NULL THEN 1
        ELSE 0
    END AS flg_mismo_producto_trip_1_2
FROM listas l
LEFT JOIN matches m
    ON l.social_id = m.social_id;

-- ============================================================
-- 9. TRANSACCIONES OBJETIVO
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_transacciones_objetivo;

CREATE TABLE tmp.rebuy_transacciones_objetivo AS
SELECT DISTINCT
    transaction_code,
    reservation_date
FROM tmp.rebuy_detalle
WHERE transaction_code IS NOT NULL;

-- ============================================================
-- 10. PATH DE MEDIOS POR TRANSACCION
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_path_totales;

CREATE TABLE tmp.rebuy_path_totales AS
WITH path_eventos AS (
    SELECT
        CAST(a.transaction_id AS VARCHAR) AS transaction_code,
        CASE
            WHEN a.event_type = 'MANUAL_ENTRY' THEN 'DIRECTO'
            WHEN a.event_type IN (
                'EMAIL', 'COM_EMAIL', 'PUSH', 'COM_PUSH', 'WEB_PUSH',
                'COM_WHATSAPP', 'SEM_WHATSAPP', 'SOCIAL_WHATSAPP',
                'ERROR_EMAIL', 'ERROR_PUSH', 'ERROR_WEB_PUSH'
            ) THEN 'CRM'
            WHEN a.event_type IN (
                'SEM_SKYSCANNER', 'SEM_TRIVAGO', 'SEM_TRIPADVISOR',
                'SEM_TURISMOCITY', 'SEM_METASEARCH', 'SEM_KAYAK',
                'SEM_MUNDI', 'SEM_HOTELS', 'SEM_HOTELS_COMBINED',
                'SEO_GOOGLE_FLIGHTS', 'SEO_GOOGLE_HOTELS',
                'ERROR_SEM_SKYSCANNER', 'ERROR_SEM_TRIVAGO',
                'ERROR_SEM_TRIPADVISOR', 'ERROR_SEM_METASEARCH',
                'ERROR_SEM_KAYAK', 'ERROR_SEM_MUNDI',
                'ERROR_SEM_HOTELS', 'ERROR_SEM_HOTELS_COMBINED'
            ) THEN 'METABUSCADORES'
            WHEN a.event_type LIKE 'SEO\_%' THEN 'SEM/SEO/KWBRAND'
            WHEN a.event_type LIKE 'SEM\_%' THEN 'SEM/SEO/KWBRAND'
            WHEN a.event_type LIKE 'BND\_%' THEN 'SEM/SEO/KWBRAND'
            WHEN a.event_type LIKE 'ERROR_SEM\_%' THEN 'SEM/SEO/KWBRAND'
            ELSE 'OTROS'
        END AS grupo_media
    FROM analytics.bi_mkt_fact_attributed_sales a
    INNER JOIN tmp.rebuy_transacciones_objetivo d
        ON CAST(a.transaction_id AS VARCHAR) = d.transaction_code
       AND a.reservation_date = d.reservation_date
    WHERE a.reservation_date IS NOT NULL
      AND CAST(a.model_id AS VARCHAR) = '33'
)
SELECT
    transaction_code,
    SUM(CASE WHEN grupo_media = 'DIRECTO' THEN 1 ELSE 0 END) AS eventos_directo,
    SUM(CASE WHEN grupo_media = 'SEM/SEO/KWBRAND' THEN 1 ELSE 0 END) AS eventos_sem_seo_kwbrand,
    SUM(CASE WHEN grupo_media = 'METABUSCADORES' THEN 1 ELSE 0 END) AS eventos_metabuscadores,
    SUM(CASE WHEN grupo_media = 'CRM' THEN 1 ELSE 0 END) AS eventos_crm,
    SUM(CASE WHEN grupo_media = 'OTROS' THEN 1 ELSE 0 END) AS eventos_otros,
    COUNT(*) AS eventos_path_total
FROM path_eventos
GROUP BY transaction_code;

-- ============================================================
-- 11. TIPO DE VUELO + FLIGHT CLASS
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_info_vuelos;

CREATE TABLE tmp.rebuy_info_vuelos AS
SELECT
    CAST(s.transaction_code AS VARCHAR) AS transaction_code,
    ARRAY_JOIN(
        ARRAY_AGG(DISTINCT CAST(s.flight_class AS VARCHAR))
        FILTER (WHERE s.flight_class IS NOT NULL),
        ' | '
    ) AS flight_class
FROM data.analytics.bi_transactional_fact_segments s
INNER JOIN (
    SELECT DISTINCT transaction_code
    FROM tmp.rebuy_detalle
    WHERE product_type = 'Vuelos'
) d
    ON CAST(s.transaction_code AS VARCHAR) = d.transaction_code
WHERE s.reservation_year_month IS NOT NULL
GROUP BY CAST(s.transaction_code AS VARCHAR);

-- ============================================================
-- 12. USO DE CUPON POR TRANSACCION
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_cupones;

CREATE TABLE tmp.rebuy_cupones AS
SELECT
    CAST(d.transaction_code AS VARCHAR) AS transaction_code,
    MAX(
        CASE
            WHEN NULLIF(TRIM(CAST(d.coupon_code AS VARCHAR)), '') IS NOT NULL
              OR NULLIF(TRIM(CAST(d.coupon_use_id AS VARCHAR)), '') IS NOT NULL
            THEN 1
            ELSE 0
        END
    ) AS flg_uso_cupon
FROM data.analytics.bi_transactional_fact_discounts d
INNER JOIN tmp.rebuy_transacciones_objetivo t
    ON CAST(d.transaction_code AS VARCHAR) = t.transaction_code
   AND d.reservation_date = t.reservation_date
WHERE d.reservation_year_month IS NOT NULL
GROUP BY CAST(d.transaction_code AS VARCHAR);

-- ============================================================
-- 13. ECONOMICS POR TRANSACCION
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_economics;

CREATE TABLE tmp.rebuy_economics AS
SELECT
    CAST(t.transaction_code AS VARCHAR) AS transaction_code,
    MAX(t.gross_bookings_usd) AS gross_bookings_usd,
    MAX(t.cost_usd) AS cost_usd,
    MAX(t.margin_variable_without_mkt_net_usd) AS margin_variable_without_mkt_net_usd,
    MAX(t.net_revenues_usd) AS net_revenues_usd,
    MAX(t.npv_without_mkt_net_usd) AS npv_without_mkt_net_usd,
    MAX(t.fee_net_usd) AS fee_net_usd
FROM analytics.mkt_users_fact_transactions t
INNER JOIN tmp.rebuy_transacciones_objetivo r
    ON CAST(t.transaction_code AS VARCHAR) = r.transaction_code
   AND t.reservation_date = r.reservation_date
WHERE t.reservation_year_month IS NOT NULL
GROUP BY CAST(t.transaction_code AS VARCHAR);

-- ============================================================
-- 14. FIRST CLICK Y LAST CLICK POR TRANSACCION
-- ============================================================
-- ============================================================
-- 13.1 FEATURES DEL SEGUNDO TRIP A NIVEL USUARIO
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_trip_2_features;

CREATE TABLE tmp.rebuy_trip_2_features AS
SELECT
    d.social_id,
    ARRAY_JOIN(
        ARRAY_AGG(DISTINCT d.destino_trip)
        FILTER (WHERE d.destino_trip IS NOT NULL),
        ' | '
    ) AS destino_trip_2,
    ARRAY_JOIN(
        ARRAY_AGG(DISTINCT d.origen_trip)
        FILTER (WHERE d.origen_trip IS NOT NULL),
        ' | '
    ) AS origen_trip_2,
    ARRAY_JOIN(
        ARRAY_AGG(DISTINCT d.tipo_viaje)
        FILTER (WHERE d.tipo_viaje IS NOT NULL),
        ' | '
    ) AS tipo_viaje_2,
    MAX(d.duracion_viaje_dias) AS duracion_viaje_dias_2,
    MAX(d.dias_anticipacion_compra_checkin) AS dias_anticipacion_compra_2,
    SUM(COALESCE(e.gross_bookings_usd, 0)) AS gross_bookings_usd_2,
    MAX(COALESCE(cp.flg_uso_cupon, 0)) AS flg_uso_cupon_2,
    ARRAY_JOIN(
        ARRAY_AGG(DISTINCT v.flight_class)
        FILTER (WHERE v.flight_class IS NOT NULL),
        ' | '
    ) AS flight_class_2
FROM tmp.rebuy_detalle d
LEFT JOIN tmp.rebuy_economics e
    ON d.transaction_code = e.transaction_code
LEFT JOIN tmp.rebuy_cupones cp
    ON d.transaction_code = cp.transaction_code
LEFT JOIN tmp.rebuy_info_vuelos v
    ON d.transaction_code = v.transaction_code
WHERE d.nro_trip = 2
GROUP BY d.social_id;

-- ============================================================
-- 14. FIRST CLICK Y LAST CLICK POR TRANSACCION
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_first_last_click;

CREATE TABLE tmp.rebuy_first_last_click AS
WITH eventos AS (
    SELECT
        CAST(a.transaction_id AS VARCHAR) AS transaction_code,
        TRY_CAST(a.click_date_time AS TIMESTAMP) AS click_datetime,
        a.event_type,
        a.event_id,
        ROW_NUMBER() OVER (
            PARTITION BY CAST(a.transaction_id AS VARCHAR)
            ORDER BY TRY_CAST(a.click_date_time AS TIMESTAMP) ASC, a.event_id ASC
        ) AS rn_first,
        ROW_NUMBER() OVER (
            PARTITION BY CAST(a.transaction_id AS VARCHAR)
            ORDER BY TRY_CAST(a.click_date_time AS TIMESTAMP) DESC, a.event_id DESC
        ) AS rn_last
    FROM analytics.bi_mkt_fact_attributed_sales a
    INNER JOIN tmp.rebuy_transacciones_objetivo t
        ON CAST(a.transaction_id AS VARCHAR) = t.transaction_code
       AND a.reservation_date = t.reservation_date
    WHERE a.reservation_date IS NOT NULL
      AND CAST(a.model_id AS VARCHAR) = '33'
      AND TRY_CAST(a.click_date_time AS TIMESTAMP) IS NOT NULL
)
SELECT
    transaction_code,
    MAX(CASE WHEN rn_first = 1 THEN click_datetime END) AS first_click_datetime,
    MAX(CASE WHEN rn_first = 1 THEN event_type END) AS first_click_event_type,
    MAX(CASE WHEN rn_last = 1 THEN click_datetime END) AS last_click_datetime,
    MAX(CASE WHEN rn_last = 1 THEN event_type END) AS last_click_event_type
FROM eventos
GROUP BY transaction_code;

-- ============================================================
-- 15. LOYALTY - PUNTOS USADOS Y TIER DE REDENCION
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_loyalty;

CREATE TABLE tmp.rebuy_loyalty AS
SELECT
    CAST(r.despegar_transaction_code AS VARCHAR) AS transaction_code,
    COALESCE(r.puntos_redimidos, 0) AS puntos_usados,
    CASE WHEN COALESCE(r.puntos_redimidos, 0) > 0 THEN 1 ELSE 0 END AS flg_uso_puntos,
    NULLIF(TRIM(r.tier), '') AS tier_redencion_raw,
    CASE
        WHEN TRIM(r.tier) LIKE '1-%' THEN '1- Viajero'
        WHEN TRIM(r.tier) LIKE '2-%' THEN '2- Explorador'
        WHEN TRIM(r.tier) LIKE '3-%' THEN '3- Global'
        ELSE NULL
    END AS tier_al_momento_redencion
FROM data.lake.loy_redemption r
INNER JOIN (
    SELECT DISTINCT transaction_code
    FROM tmp.rebuy_transacciones_objetivo
) t
    ON CAST(r.despegar_transaction_code AS VARCHAR) = t.transaction_code
WHERE r.despegar_transaction_code IS NOT NULL
  AND r.flg_cancelado = 0
  AND r.flg_error = 0;

-- ============================================================
-- 16. CUSTOMER SERVICE / NPS POR TRANSACCION
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_customer_service;

CREATE TABLE tmp.rebuy_customer_service AS
SELECT
    CAST(n.transaction_code AS VARCHAR) AS transaction_code,
    1 AS flg_customer_service,
    COUNT(*) AS cantidad_interacciones_cs,
    COUNT(DISTINCT n.conversation_id) AS cantidad_conversaciones_cs,
    MAX(CASE WHEN n.nps = 'Satisfecho' THEN 1 ELSE 0 END) AS flg_cs_satisfecho,
    MAX(CASE WHEN n.nps = 'Neutro' THEN 1 ELSE 0 END) AS flg_cs_neutro,
    MAX(CASE WHEN n.nps = 'Insatisfecho' THEN 1 ELSE 0 END) AS flg_cs_insatisfecho,
    MAX(CASE WHEN n.nps = 'NA' THEN 1 ELSE 0 END) AS flg_cs_nps_na,
    MAX(CASE WHEN n.resolution = 'Si' THEN 1 ELSE 0 END) AS flg_cs_resuelto,
    MAX(CASE WHEN n.resolution = 'No' THEN 1 ELSE 0 END) AS flg_cs_no_resuelto,
    AVG(TRY_CAST(n.agent_empathy AS DOUBLE)) AS avg_agent_empathy_cs,
    MIN(TRY_CAST(n.agent_empathy AS DOUBLE)) AS min_agent_empathy_cs,
    MAX(TRY_CAST(n.agent_empathy AS DOUBLE)) AS max_agent_empathy_cs
FROM data.analytics.as_omnichannel_fact_customer_experience n
INNER JOIN (
    SELECT DISTINCT transaction_code
    FROM tmp.rebuy_transacciones_objetivo
) t
    ON CAST(n.transaction_code AS VARCHAR) = t.transaction_code
WHERE n.transaction_code IS NOT NULL
GROUP BY CAST(n.transaction_code AS VARCHAR);

-- ============================================================
-- 17. VISITAS APP
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_app_visits;

CREATE TABLE tmp.rebuy_app_visits AS
WITH rango AS (
    SELECT
        DATE_ADD('day', -90, MIN(CAST(fecha_primer_trip AS DATE))) AS fecha_min,
        DATE_ADD(
            'day',
            90,
            MAX(
                COALESCE(
                    CAST(fecha_segundo_trip AS DATE),
                    CAST(fecha_primer_trip AS DATE)
                )
            )
        ) AS fecha_max
    FROM tmp.rebuy_usuarios_validos
),
socials_rebuy AS (
    SELECT DISTINCT social_id
    FROM tmp.rebuy_usuarios_validos
)
SELECT
    CAST(v.social_id AS VARCHAR) AS social_id,
    v.visit_id,
    CAST(v.start_visit AS TIMESTAMP) AS visit_datetime
FROM analytics.mkt_users_fact_visits v
INNER JOIN socials_rebuy s
    ON CAST(v.social_id AS VARCHAR) = s.social_id
CROSS JOIN rango r
WHERE v.visit_date >= CAST(DATE_ADD('year', -10, CURRENT_DATE) AS VARCHAR)
  AND v.visit_date <= CAST(CURRENT_DATE AS VARCHAR)
  AND v.visit_date >= CAST(r.fecha_min AS VARCHAR)
  AND v.visit_date <= CAST(r.fecha_max AS VARCHAR)
  AND UPPER(TRIM(v.company)) = 'DESPEGAR'
  AND v.main_channel IN ('iphone-app', 'android-app')
  AND v.social_id IS NOT NULL
  AND v.visit_id IS NOT NULL;

-- ============================================================
-- 18. COMPORTAMIENTO APP RESPECTO A TRIP 1 Y TRIP 2
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_app_behavior;

CREATE TABLE tmp.rebuy_app_behavior AS
SELECT
    u.social_id,
    MAX(
        CASE
            WHEN a.visit_datetime >= DATE_ADD('day', -90, CAST(u.fecha_primer_trip AS TIMESTAMP))
             AND a.visit_datetime < CAST(u.fecha_primer_trip AS TIMESTAMP)
            THEN 1 ELSE 0
        END
    ) AS flg_app_90d_antes_trip1,
    COUNT(
        DISTINCT CASE
            WHEN a.visit_datetime >= DATE_ADD('day', -90, CAST(u.fecha_primer_trip AS TIMESTAMP))
             AND a.visit_datetime < CAST(u.fecha_primer_trip AS TIMESTAMP)
            THEN a.visit_id
        END
    ) AS visitas_app_90d_antes_trip1,
    MAX(
        CASE
            WHEN u.fecha_segundo_trip IS NOT NULL
             AND a.visit_datetime > CAST(u.fecha_primer_trip AS TIMESTAMP)
             AND a.visit_datetime < CAST(u.fecha_segundo_trip AS TIMESTAMP)
            THEN 1 ELSE 0
        END
    ) AS flg_app_entre_trips,
    COUNT(
        DISTINCT CASE
            WHEN u.fecha_segundo_trip IS NOT NULL
             AND a.visit_datetime > CAST(u.fecha_primer_trip AS TIMESTAMP)
             AND a.visit_datetime < CAST(u.fecha_segundo_trip AS TIMESTAMP)
            THEN a.visit_id
        END
    ) AS visitas_app_entre_trips,
    MAX(
        CASE
            WHEN a.visit_datetime > CAST(u.fecha_primer_trip AS TIMESTAMP)
             AND a.visit_datetime <= DATE_ADD('day', 90, CAST(u.fecha_primer_trip AS TIMESTAMP))
            THEN 1 ELSE 0
        END
    ) AS flg_app_90d_post_trip1,
    COUNT(
        DISTINCT CASE
            WHEN a.visit_datetime > CAST(u.fecha_primer_trip AS TIMESTAMP)
             AND a.visit_datetime <= DATE_ADD('day', 90, CAST(u.fecha_primer_trip AS TIMESTAMP))
            THEN a.visit_id
        END
    ) AS visitas_app_90d_post_trip1,
    MAX(
        CASE
            WHEN a.visit_datetime < CAST(u.fecha_primer_trip AS TIMESTAMP)
            THEN a.visit_datetime
        END
    ) AS ultima_visita_app_antes_trip1,
    MAX(
        CASE
            WHEN u.fecha_segundo_trip IS NOT NULL
             AND a.visit_datetime < CAST(u.fecha_segundo_trip AS TIMESTAMP)
            THEN a.visit_datetime
        END
    ) AS ultima_visita_app_antes_trip2
FROM tmp.rebuy_usuarios_validos u
LEFT JOIN tmp.rebuy_app_visits a
    ON u.social_id = a.social_id
GROUP BY u.social_id;

-- ============================================================
-- 19. METODOS DE PAGO POR TRANSACCION
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_metodos_pago;

CREATE TABLE tmp.rebuy_metodos_pago AS
WITH dim_payments AS (
    SELECT
        payment_user_id,
        social_id,
        payment_type,
        bank,
        tier
    FROM analytics.mkt_users_dim_payments
    WHERE payment_type IS NOT NULL
),
base AS (
    SELECT
        CAST(p.transaction_code AS VARCHAR) AS transaction_code,
        p.payment_method_id,
        p.payment_user_id,
        d.payment_type,
        d.bank,
        d.tier,
        COALESCE(p.gross_bookings_usd, 0) AS gross_bookings_usd
    FROM analytics.mkt_users_fact_payments p
    INNER JOIN (
        SELECT DISTINCT transaction_code
        FROM tmp.rebuy_transacciones_objetivo
    ) t
        ON CAST(p.transaction_code AS VARCHAR) = t.transaction_code
    LEFT JOIN dim_payments d
        ON p.payment_user_id = d.payment_user_id
       AND p.social_id = d.social_id
    WHERE p.reservation_year_month IS NOT NULL
      AND p.transaction_code IS NOT NULL
),
agg AS (
    SELECT
        transaction_code,
        COUNT(DISTINCT payment_method_id) AS cantidad_pagos,
        COUNT(DISTINCT payment_user_id) AS cantidad_instrumentos_pago,
        COUNT(DISTINCT payment_type) AS cantidad_tipos_pago,
        ARRAY_JOIN(
            ARRAY_SORT(
                ARRAY_AGG(DISTINCT payment_type)
                FILTER (WHERE payment_type IS NOT NULL)
            ),
            ' | '
        ) AS metodos_pago,
        ARRAY_JOIN(
            ARRAY_SORT(
                ARRAY_AGG(DISTINCT bank)
                FILTER (
                    WHERE payment_type = 'Tarjeta de Crédito'
                      AND NULLIF(TRIM(bank), '') IS NOT NULL
                )
            ),
            ' | '
        ) AS bancos_tarjeta,
        ARRAY_JOIN(
            ARRAY_SORT(
                ARRAY_AGG(DISTINCT tier)
                FILTER (
                    WHERE payment_type = 'Tarjeta de Crédito'
                      AND NULLIF(TRIM(tier), '') IS NOT NULL
                )
            ),
            ' | '
        ) AS tiers_tarjeta,
        SUM(gross_bookings_usd) AS gb_total_payments,
        SUM(CASE WHEN payment_type = 'Tarjeta de Crédito' THEN gross_bookings_usd ELSE 0 END) AS gb_tarjeta_credito,
        SUM(CASE WHEN payment_type = 'Transferencia' THEN gross_bookings_usd ELSE 0 END) AS gb_transferencia,
        SUM(CASE WHEN payment_type = 'Depósito Bancario' THEN gross_bookings_usd ELSE 0 END) AS gb_deposito_bancario,
        SUM(CASE WHEN payment_type = 'Puntos Loyalty' THEN gross_bookings_usd ELSE 0 END) AS gb_puntos_loyalty,
        SUM(CASE WHEN payment_type = 'Cupón' THEN gross_bookings_usd ELSE 0 END) AS gb_cupon,
        SUM(CASE WHEN payment_type = 'Cash' THEN gross_bookings_usd ELSE 0 END) AS gb_cash,
        MAX(CASE WHEN payment_type = 'Tarjeta de Crédito' THEN 1 ELSE 0 END) AS flg_tarjeta_credito,
        MAX(CASE WHEN payment_type = 'Transferencia' THEN 1 ELSE 0 END) AS flg_transferencia,
        MAX(CASE WHEN payment_type = 'Depósito Bancario' THEN 1 ELSE 0 END) AS flg_deposito_bancario,
        MAX(CASE WHEN payment_type = 'Puntos Loyalty' THEN 1 ELSE 0 END) AS flg_puntos_loyalty_pago,
        MAX(CASE WHEN payment_type = 'Cupón' THEN 1 ELSE 0 END) AS flg_cupon_pago,
        MAX(CASE WHEN payment_type = 'Cash' THEN 1 ELSE 0 END) AS flg_cash
    FROM base
    GROUP BY transaction_code
)
SELECT
    transaction_code,
    cantidad_pagos,
    cantidad_instrumentos_pago,
    cantidad_tipos_pago,
    CASE WHEN cantidad_instrumentos_pago > 1 THEN 1 ELSE 0 END AS flg_multi_instrumento_pago,
    CASE WHEN cantidad_tipos_pago > 1 THEN 1 ELSE 0 END AS flg_multi_tipo_pago,
    metodos_pago,
    bancos_tarjeta,
    tiers_tarjeta,
    gb_total_payments,
    gb_tarjeta_credito,
    gb_transferencia,
    gb_deposito_bancario,
    gb_puntos_loyalty,
    gb_cupon,
    gb_cash,
    CASE WHEN gb_total_payments <> 0 THEN gb_tarjeta_credito / gb_total_payments END AS pct_gb_tarjeta_credito,
    CASE WHEN gb_total_payments <> 0 THEN gb_transferencia / gb_total_payments END AS pct_gb_transferencia,
    CASE WHEN gb_total_payments <> 0 THEN gb_deposito_bancario / gb_total_payments END AS pct_gb_deposito_bancario,
    CASE WHEN gb_total_payments <> 0 THEN gb_puntos_loyalty / gb_total_payments END AS pct_gb_puntos_loyalty,
    CASE WHEN gb_total_payments <> 0 THEN gb_cupon / gb_total_payments END AS pct_gb_cupon,
    CASE WHEN gb_total_payments <> 0 THEN gb_cash / gb_total_payments END AS pct_gb_cash,
    flg_tarjeta_credito,
    flg_transferencia,
    flg_deposito_bancario,
    flg_puntos_loyalty_pago,
    flg_cupon_pago,
    flg_cash
FROM agg;

-- ============================================================
-- 20. PERFIL USUARIO: EDAD, INCOME, RESIDENCIA Y GEO
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_perfil_usuario;

CREATE TABLE tmp.rebuy_perfil_usuario AS
WITH users_rn AS (
    SELECT
        CAST(u.social_id AS VARCHAR) AS social_id,
        u.creation_date,
        u.birth_year,
        u.income,
        u.nationality,
        u.country_code,
        u.state_code,
        u.state_name,
        u.city_id,
        u.city_code,
        u.city_name,
        u.last_visit_geolocation_city_code,
        u.last_visit_geolocation_country_code,
        u.frequent_visit_geolocation_city_code,
        u.frequent_visit_geolocation_country_code,
        u.last_transaction_geolocation_city_code,
        u.last_transaction_geolocation_country_code,
        ROW_NUMBER() OVER (
            PARTITION BY CAST(u.social_id AS VARCHAR)
            ORDER BY u.audit_datetime DESC
        ) AS rn
    FROM analytics.mkt_users_dim_users u
    INNER JOIN tmp.rebuy_usuarios_validos r
        ON CAST(u.social_id AS VARCHAR) = r.social_id
    WHERE u.creation_date >= DATE '1900-01-01'
      AND u.company = 'Despegar'
      AND u.social_id IS NOT NULL
),
users AS (
    SELECT *
    FROM users_rn
    WHERE rn = 1
)
SELECT
    r.social_id,
    u.creation_date AS fecha_creacion_usuario,
    u.birth_year,
    CASE
        WHEN u.birth_year IS NOT NULL
         AND YEAR(CAST(r.fecha_primer_trip AS DATE)) - u.birth_year BETWEEN 0 AND 110
        THEN YEAR(CAST(r.fecha_primer_trip AS DATE)) - u.birth_year
    END AS edad_aprox_primer_trip,
    CASE
        WHEN u.birth_year IS NULL THEN 'Sin dato'
        WHEN YEAR(CAST(r.fecha_primer_trip AS DATE)) - u.birth_year < 0 THEN 'Edad invalida'
        WHEN YEAR(CAST(r.fecha_primer_trip AS DATE)) - u.birth_year < 18 THEN '<18'
        WHEN YEAR(CAST(r.fecha_primer_trip AS DATE)) - u.birth_year BETWEEN 18 AND 24 THEN '18-24'
        WHEN YEAR(CAST(r.fecha_primer_trip AS DATE)) - u.birth_year BETWEEN 25 AND 34 THEN '25-34'
        WHEN YEAR(CAST(r.fecha_primer_trip AS DATE)) - u.birth_year BETWEEN 35 AND 44 THEN '35-44'
        WHEN YEAR(CAST(r.fecha_primer_trip AS DATE)) - u.birth_year BETWEEN 45 AND 54 THEN '45-54'
        WHEN YEAR(CAST(r.fecha_primer_trip AS DATE)) - u.birth_year BETWEEN 55 AND 64 THEN '55-64'
        WHEN YEAR(CAST(r.fecha_primer_trip AS DATE)) - u.birth_year BETWEEN 65 AND 110 THEN '65+'
        ELSE 'Edad invalida'
    END AS rango_edad_primer_trip,
    NULLIF(TRIM(u.income), '') AS income,
    NULLIF(TRIM(u.nationality), '') AS nationality,
    NULLIF(TRIM(u.country_code), '') AS pais_residencia,
    NULLIF(TRIM(u.state_code), '') AS estado_residencia_codigo,
    NULLIF(TRIM(u.state_name), '') AS estado_residencia,
    NULLIF(TRIM(u.city_id), '') AS ciudad_residencia_id,
    NULLIF(TRIM(u.city_code), '') AS ciudad_residencia_codigo,
    NULLIF(TRIM(u.city_name), '') AS ciudad_residencia,
    NULLIF(TRIM(u.last_visit_geolocation_city_code), '') AS geo_ultima_visita_ciudad,
    NULLIF(TRIM(u.last_visit_geolocation_country_code), '') AS geo_ultima_visita_pais,
    NULLIF(TRIM(u.frequent_visit_geolocation_city_code), '') AS geo_visita_frecuente_ciudad,
    NULLIF(TRIM(u.frequent_visit_geolocation_country_code), '') AS geo_visita_frecuente_pais,
    NULLIF(TRIM(u.last_transaction_geolocation_city_code), '') AS geo_ultima_transaccion_ciudad,
    NULLIF(TRIM(u.last_transaction_geolocation_country_code), '') AS geo_ultima_transaccion_pais,
    CASE
        WHEN u.creation_date IS NOT NULL
         AND CAST(r.fecha_primer_trip AS DATE) >= u.creation_date
        THEN DATE_DIFF(
            'day',
            u.creation_date,
            CAST(r.fecha_primer_trip AS DATE)
        )
    END AS antiguedad_usuario_dias_al_trip1
FROM tmp.rebuy_usuarios_validos r
LEFT JOIN users u
    ON r.social_id = u.social_id;

-- ============================================================
-- 20.1 CANTIDAD DE PASAJEROS POR TRANSACCION Y PRODUCTO
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_pasajeros;

CREATE TABLE tmp.rebuy_pasajeros AS
SELECT
    CAST(fp.transaction_code AS VARCHAR) AS transaction_code,
    fp.product_type,
    MAX(fp.adults_quantity) AS adultos,
    MAX(fp.childs_quantity) AS ninos,
    MAX(fp.infants_quantity) AS infantes,
    MAX(fp.total_passengers_quantity) AS cantidad_pasajeros
FROM data.analytics.bi_transactional_fact_products fp
INNER JOIN (
    SELECT DISTINCT transaction_code, product_type
    FROM tmp.rebuy_detalle
    WHERE product_type IS NOT NULL
) d
    ON CAST(fp.transaction_code AS VARCHAR) = d.transaction_code
   AND fp.product_type = d.product_type
WHERE fp.reservation_year_month IS NOT NULL
GROUP BY
    CAST(fp.transaction_code AS VARCHAR),
    fp.product_type;

-- ============================================================
-- 20.2 CANTIDAD DE PASAJEROS Y TIPO DE VIAJERO POR VIAJE (TRIP_ID)
-- ============================================================
-- Regla tipo_viajero (prioridad en ese orden):
--   1. Si viajan ninos o infantes (en cualquier producto del viaje)   -> Familia
--   2. Si viaja 1 solo adulto y no hay ninos/infantes                -> Solo
--   3. Si viajan 2 o mas adultos y no hay ninos/infantes             -> Pareja/Amigos
--      (no se puede distinguir pareja de amigos con los datos
--       disponibles: no hay tabla de pasajeros con relacion/edad,
--       ni estado civil en mkt_users_dim_users)
--   4. Si no hay dato de pasajeros                                   -> Sin dato
DROP TABLE IF EXISTS tmp.rebuy_pasajeros_viaje;

CREATE TABLE tmp.rebuy_pasajeros_viaje AS
WITH agg AS (
    SELECT
        d.social_id,
        d.trip_id,
        MAX(pq.adultos) AS adultos_viaje,
        MAX(pq.ninos) AS ninos_viaje,
        MAX(pq.infantes) AS infantes_viaje,
        MAX(pq.cantidad_pasajeros) AS cantidad_pasajeros_viaje
    FROM tmp.rebuy_detalle d
    LEFT JOIN tmp.rebuy_pasajeros pq
        ON d.transaction_code = pq.transaction_code
       AND d.product_type = pq.product_type
    GROUP BY
        d.social_id,
        d.trip_id
)
SELECT
    social_id,
    trip_id,
    adultos_viaje,
    ninos_viaje,
    infantes_viaje,
    cantidad_pasajeros_viaje,
    CASE
        WHEN COALESCE(ninos_viaje, 0) > 0 OR COALESCE(infantes_viaje, 0) > 0 THEN 'Familia'
        WHEN adultos_viaje = 1 THEN 'Solo'
        WHEN adultos_viaje >= 2 THEN 'Pareja/Amigos'
        ELSE 'Sin dato'
    END AS tipo_viajero
FROM agg;

-- ============================================================
-- 21. TABLA FINAL CONSOLIDADA
-- ============================================================
DROP TABLE IF EXISTS tmp.rebuy_final;

CREATE TABLE tmp.rebuy_final AS
SELECT
    d.social_id,
    d.nro_trip,
    d.trip_id,
    d.transaction_code,
    d.purchase_type,
    d.product_type,
    d.pais,
    d.tipo_viaje,
    d.plataforma_compra,
    d.canal_compra_agrupado,
    c.plataforma_trip_1,
    c.plataforma_trip_2,
    c.canales_compra_trip_1,
    c.canales_compra_trip_2,
    d.origen_trip,
    d.destino_trip,
    v.flight_class,
    t2.destino_trip_2,
    t2.origen_trip_2,
    t2.tipo_viaje_2,
    t2.duracion_viaje_dias_2,
    t2.dias_anticipacion_compra_2,
    t2.gross_bookings_usd_2,
    COALESCE(t2.flg_uso_cupon_2, 0) AS flg_uso_cupon_2,
    t2.flight_class_2,
    d.reservation_date,
    d.reservation_datetime,
    d.fecha_primer_trip,
    d.fecha_segundo_trip,
    d.tipo_usuario,

    -- PERFIL USUARIO
    pu.birth_year,
    pu.edad_aprox_primer_trip,
    pu.rango_edad_primer_trip,
    pu.income,
    pu.nationality,
    pu.pais_residencia,
    pu.estado_residencia_codigo,
    pu.estado_residencia,
    pu.ciudad_residencia_id,
    pu.ciudad_residencia_codigo,
    pu.ciudad_residencia,
    pu.fecha_creacion_usuario,
    pu.antiguedad_usuario_dias_al_trip1,

    -- GEO ULTIMO ESTADO CONOCIDO
    pu.geo_ultima_visita_ciudad,
    pu.geo_ultima_visita_pais,
    pu.geo_visita_frecuente_ciudad,
    pu.geo_visita_frecuente_pais,
    pu.geo_ultima_transaccion_ciudad,
    pu.geo_ultima_transaccion_pais,

    -- VIAJE
    d.trip_checkin,
    d.trip_checkout,
    d.dias_anticipacion_compra_checkin,
    d.duracion_viaje_dias,
    CASE
        WHEN d.dias_anticipacion_compra_checkin < 0 THEN 'Invalido'
        WHEN d.dias_anticipacion_compra_checkin BETWEEN 0 AND 6 THEN '0-6 dias'
        WHEN d.dias_anticipacion_compra_checkin BETWEEN 7 AND 29 THEN '7-29 dias'
        WHEN d.dias_anticipacion_compra_checkin BETWEEN 30 AND 59 THEN '30-59 dias'
        WHEN d.dias_anticipacion_compra_checkin BETWEEN 60 AND 89 THEN '60-89 dias'
        WHEN d.dias_anticipacion_compra_checkin >= 90 THEN '90+ dias'
    END AS bucket_anticipacion_compra,
    CASE
        WHEN d.duracion_viaje_dias < 0 THEN 'Invalido'
        WHEN d.duracion_viaje_dias = 0 THEN 'Mismo dia'
        WHEN d.duracion_viaje_dias BETWEEN 1 AND 3 THEN '1-3 dias'
        WHEN d.duracion_viaje_dias BETWEEN 4 AND 7 THEN '4-7 dias'
        WHEN d.duracion_viaje_dias BETWEEN 8 AND 14 THEN '8-14 dias'
        WHEN d.duracion_viaje_dias >= 15 THEN '15+ dias'
    END AS bucket_duracion_viaje,
    CASE
        WHEN d.fecha_segundo_trip IS NOT NULL
        THEN DATE_DIFF(
            'day',
            CAST(d.fecha_primer_trip AS DATE),
            CAST(d.fecha_segundo_trip AS DATE)
        )
    END AS dias_entre_trip_1_y_2,

    -- PASAJEROS (por producto)
    pq.cantidad_pasajeros,

    -- PASAJEROS Y TIPO DE VIAJERO (por viaje / trip_id)
    pv.adultos_viaje,
    pv.ninos_viaje,
    pv.infantes_viaje,
    pv.cantidad_pasajeros_viaje,
    pv.tipo_viajero,

    -- APP
    COALESCE(ab.flg_app_90d_antes_trip1, 0) AS flg_app_90d_antes_trip1,
    COALESCE(ab.visitas_app_90d_antes_trip1, 0) AS visitas_app_90d_antes_trip1,
    COALESCE(ab.flg_app_entre_trips, 0) AS flg_app_entre_trips,
    COALESCE(ab.visitas_app_entre_trips, 0) AS visitas_app_entre_trips,
    COALESCE(ab.flg_app_90d_post_trip1, 0) AS flg_app_90d_post_trip1,
    COALESCE(ab.visitas_app_90d_post_trip1, 0) AS visitas_app_90d_post_trip1,
    ab.ultima_visita_app_antes_trip1,
    ab.ultima_visita_app_antes_trip2,

    -- FIRST / LAST CLICK
    fc.first_click_datetime,
    fc.first_click_event_type,
    fc.last_click_datetime,
    fc.last_click_event_type,

    -- ECONOMICS
    e.gross_bookings_usd,
    e.cost_usd,
    e.margin_variable_without_mkt_net_usd,
    e.net_revenues_usd,
    e.npv_without_mkt_net_usd,
    e.fee_net_usd,

    -- LOYALTY
    COALESCE(l.puntos_usados, 0) AS puntos_usados,
    COALESCE(l.flg_uso_puntos, 0) AS flg_uso_puntos,
    l.tier_redencion_raw,
    l.tier_al_momento_redencion,

    -- METODOS DE PAGO
    mp.metodos_pago,
    mp.bancos_tarjeta,
    mp.tiers_tarjeta,
    mp.cantidad_pagos,
    mp.cantidad_instrumentos_pago,
    mp.cantidad_tipos_pago,
    mp.flg_multi_instrumento_pago,
    mp.flg_multi_tipo_pago,
    mp.gb_total_payments,
    mp.gb_tarjeta_credito,
    mp.gb_transferencia,
    mp.gb_deposito_bancario,
    mp.gb_puntos_loyalty,
    mp.gb_cupon,
    mp.gb_cash,
    mp.pct_gb_tarjeta_credito,
    mp.pct_gb_transferencia,
    mp.pct_gb_deposito_bancario,
    mp.pct_gb_puntos_loyalty,
    mp.pct_gb_cupon,
    mp.pct_gb_cash,
    COALESCE(mp.flg_tarjeta_credito, 0) AS flg_tarjeta_credito,
    COALESCE(mp.flg_transferencia, 0) AS flg_transferencia,
    COALESCE(mp.flg_deposito_bancario, 0) AS flg_deposito_bancario,
    COALESCE(mp.flg_puntos_loyalty_pago, 0) AS flg_puntos_loyalty_pago,
    COALESCE(mp.flg_cupon_pago, 0) AS flg_cupon_pago,
    COALESCE(mp.flg_cash, 0) AS flg_cash,

    -- CUSTOMER SERVICE
    COALESCE(cs.flg_customer_service, 0) AS flg_customer_service,
    COALESCE(cs.cantidad_interacciones_cs, 0) AS cantidad_interacciones_cs,
    COALESCE(cs.cantidad_conversaciones_cs, 0) AS cantidad_conversaciones_cs,
    COALESCE(cs.flg_cs_satisfecho, 0) AS flg_cs_satisfecho,
    COALESCE(cs.flg_cs_neutro, 0) AS flg_cs_neutro,
    COALESCE(cs.flg_cs_insatisfecho, 0) AS flg_cs_insatisfecho,
    COALESCE(cs.flg_cs_nps_na, 0) AS flg_cs_nps_na,
    COALESCE(cs.flg_cs_resuelto, 0) AS flg_cs_resuelto,
    COALESCE(cs.flg_cs_no_resuelto, 0) AS flg_cs_no_resuelto,
    cs.avg_agent_empathy_cs,
    cs.min_agent_empathy_cs,
    cs.max_agent_empathy_cs,

    -- PRODUCTOS
    ps.productos_trip_1,
    ps.productos_trip_2,
    COALESCE(ps.flg_mismo_producto_trip_1_2, 0) AS flg_mismo_producto_trip_1_2,

    -- CUPON
    COALESCE(cp.flg_uso_cupon, 0) AS flg_uso_cupon,

    -- ACTIVIDAD ENTRE TRIPS
    COALESCE(ae.cantidad_visitas_entre_trips, 0) AS cantidad_visitas_entre_trips,
    COALESCE(ae.cantidad_searches_entre_trips, 0) AS cantidad_searches_entre_trips,

    -- PATH DE MEDIOS
    COALESCE(p.eventos_directo, 0) AS eventos_directo,
    COALESCE(p.eventos_sem_seo_kwbrand, 0) AS eventos_sem_seo_kwbrand,
    COALESCE(p.eventos_metabuscadores, 0) AS eventos_metabuscadores,
    COALESCE(p.eventos_crm, 0) AS eventos_crm,
    COALESCE(p.eventos_otros, 0) AS eventos_otros,
    COALESCE(p.eventos_path_total, 0) AS eventos_path_total
FROM tmp.rebuy_detalle d
LEFT JOIN tmp.rebuy_compra_por_trip c
    ON d.social_id = c.social_id
LEFT JOIN tmp.rebuy_productos_social ps
    ON d.social_id = ps.social_id
LEFT JOIN tmp.rebuy_trip_2_features t2
    ON d.social_id = t2.social_id
LEFT JOIN tmp.rebuy_info_vuelos v
    ON d.transaction_code = v.transaction_code
LEFT JOIN tmp.rebuy_pasajeros pq
    ON d.transaction_code = pq.transaction_code
   AND d.product_type = pq.product_type
LEFT JOIN tmp.rebuy_pasajeros_viaje pv
    ON d.social_id = pv.social_id
   AND d.trip_id = pv.trip_id
LEFT JOIN tmp.rebuy_path_totales p
    ON d.transaction_code = p.transaction_code
LEFT JOIN tmp.rebuy_actividad_entre_trips ae
    ON d.social_id = ae.social_id
LEFT JOIN tmp.rebuy_cupones cp
    ON d.transaction_code = cp.transaction_code
LEFT JOIN tmp.rebuy_first_last_click fc
    ON d.transaction_code = fc.transaction_code
LEFT JOIN tmp.rebuy_economics e
    ON d.transaction_code = e.transaction_code
LEFT JOIN tmp.rebuy_loyalty l
    ON d.transaction_code = l.transaction_code
LEFT JOIN tmp.rebuy_customer_service cs
    ON d.transaction_code = cs.transaction_code
LEFT JOIN tmp.rebuy_app_behavior ab
    ON d.social_id = ab.social_id
LEFT JOIN tmp.rebuy_metodos_pago mp
    ON d.transaction_code = mp.transaction_code
LEFT JOIN tmp.rebuy_perfil_usuario pu
    ON d.social_id = pu.social_id;

-- ============================================================
-- 22. CONTROLES FINALES
-- ============================================================

-- 22.1 METODOS DE PAGO: 1 FILA POR TRANSACTION_CODE
SELECT
    COUNT(*) AS filas,
    COUNT(DISTINCT transaction_code) AS transacciones
FROM tmp.rebuy_metodos_pago;

-- 22.2 APP BEHAVIOR: 1 FILA POR SOCIAL_ID
SELECT
    COUNT(*) AS filas,
    COUNT(DISTINCT social_id) AS socials,
    COUNT(DISTINCT CASE WHEN flg_app_90d_antes_trip1 = 1 THEN social_id END) AS users_app_90d_antes_trip1,
    COUNT(DISTINCT CASE WHEN flg_app_entre_trips = 1 THEN social_id END) AS users_app_entre_trips,
    COUNT(DISTINCT CASE WHEN flg_app_90d_post_trip1 = 1 THEN social_id END) AS users_app_90d_post_trip1
FROM tmp.rebuy_app_behavior;

-- 22.3 PERFIL USUARIO: 1 FILA POR SOCIAL_ID + COMPLETITUD
SELECT
    COUNT(*) AS filas,
    COUNT(DISTINCT social_id) AS socials,
    COUNT(DISTINCT CASE WHEN edad_aprox_primer_trip IS NOT NULL THEN social_id END) AS users_con_edad,
    COUNT(DISTINCT CASE WHEN income IS NOT NULL THEN social_id END) AS users_con_income,
    COUNT(DISTINCT CASE WHEN pais_residencia IS NOT NULL THEN social_id END) AS users_con_pais_residencia,
    COUNT(DISTINCT CASE WHEN estado_residencia IS NOT NULL THEN social_id END) AS users_con_estado_residencia,
    COUNT(DISTINCT CASE WHEN ciudad_residencia IS NOT NULL THEN social_id END) AS users_con_ciudad_residencia,
    COUNT(DISTINCT CASE WHEN geo_visita_frecuente_ciudad IS NOT NULL THEN social_id END) AS users_con_geo_frecuente
FROM tmp.rebuy_perfil_usuario;

-- 22.4 TIPO DE VIAJE
SELECT
    tipo_viaje,
    COUNT(*) AS filas,
    COUNT(DISTINCT social_id) AS usuarios,
    COUNT(DISTINCT transaction_code) AS transacciones
FROM tmp.rebuy_final
GROUP BY tipo_viaje
ORDER BY filas DESC;

-- 22.5 CHECKIN / CHECKOUT / ANTICIPACION / DURACION
SELECT
    COUNT(*) AS filas,
    COUNT(CASE WHEN trip_checkin IS NOT NULL THEN 1 END) AS con_checkin,
    COUNT(CASE WHEN trip_checkout IS NOT NULL THEN 1 END) AS con_checkout,
    COUNT(CASE WHEN dias_anticipacion_compra_checkin IS NOT NULL THEN 1 END) AS con_anticipacion,
    COUNT(CASE WHEN dias_anticipacion_compra_checkin < 0 THEN 1 END) AS anticipacion_invalida,
    COUNT(CASE WHEN duracion_viaje_dias IS NOT NULL THEN 1 END) AS con_duracion,
    COUNT(CASE WHEN duracion_viaje_dias < 0 THEN 1 END) AS duracion_invalida
FROM tmp.rebuy_final;

-- 22.6 TABLA FINAL
SELECT
    COUNT(*) AS filas_final,
    COUNT(DISTINCT social_id) AS usuarios,
    COUNT(DISTINCT transaction_code) AS transacciones
FROM tmp.rebuy_final;

-- 22.7 MUESTRA
SELECT *
FROM tmp.rebuy_final
ORDER BY
    social_id,
    nro_trip,
    reservation_datetime,
    transaction_code,
    product_type
LIMIT 100;

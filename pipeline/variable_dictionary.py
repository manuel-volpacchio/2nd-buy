"""
Diccionario de variables de tmp.rebuy_final, clasificadas por temporalidad y
riesgo de leakage. Es la fuente de verdad unica que usan el resto de los
scripts (modelado, dashboard, informes) para decidir que variable entra
en cada analisis. Ver resumen_pipeline_rebuy.pdf y el SQL para el detalle
de cada fuente.

group:
  A = disponible al momento de trip1 (segura para prediccion)
  B = observable despues de trip1, con ventana de observacion controlable
      (usable si se corta correctamente / se documenta la contaminacion)
  C = leakage directo o indirecto del target (segundo trip) -> NUNCA como feature
  D = descriptiva pura, con problema de cobertura o temporalidad no resuelta
      (no se usa como feature; se reporta solo de forma descriptiva)
"""

VARIABLES = [
    # ---- identificadores / target ----
    {"name": "social_id", "group": "id", "source": "grano", "usable_model": False,
     "note": "Identificador de usuario, no es feature."},
    {"name": "fecha_primer_trip", "group": "A", "source": "clientes_trips_fact", "usable_model": "solo como ancla temporal (cohorte), no como feature del modelo",
     "note": "Define la cohorte y el punto t=0 de toda ventana."},
    {"name": "fecha_segundo_trip", "group": "C", "source": "clientes_trips_fact", "usable_model": False,
     "note": "Es el evento objetivo. Nunca se usa como feature."},

    # ---- Grupo A: trip1 ----
    {"name": "pais", "group": "A", "source": "clientes_trips_fact (trip1)", "usable_model": True, "note": ""},
    {"name": "purchase_type / product_type (trip1)", "group": "A", "source": "clientes_trips_fact (trip1)", "usable_model": True, "note": "Producto principal de la transaccion representativa de trip1."},
    {"name": "plataforma_trip_1", "group": "A", "source": "mkt_users_fact_transactions", "usable_model": True, "note": "Puede ser multivalor si trip1 tuvo mas de una transaccion en plataformas distintas."},
    {"name": "canales_compra_trip_1", "group": "A", "source": "mkt_users_fact_transactions", "usable_model": True, "note": "Idem, multivalor posible."},
    {"name": "origen_trip / destino_trip", "group": "A", "source": "clientes_trips_fact (trip1)", "usable_model": True, "note": "Alta cardinalidad; usar con agrupamientos (region/top aeropuertos)."},
    {"name": "flight_class (trip1)", "group": "A", "source": "bi_transactional_fact_segments", "usable_model": True, "note": "NULL estructural para no-Vuelos; no es missing real en ese caso."},
    {"name": "flg_uso_cupon (trip1)", "group": "A", "source": "bi_transactional_fact_discounts", "usable_model": True, "note": ""},
    {"name": "flg_uso_puntos / puntos_usados (trip1)", "group": "A", "source": "loy_redemption", "usable_model": True, "note": "Incidencia baja y creciente en el tiempo (ver disclaimer cobertura)."},
    {"name": "tier_al_momento_redencion (trip1)", "group": "A", "source": "loy_redemption", "usable_model": True, "note": "Solo no-nulo si hubo redencion de puntos en trip1 (~3% de las transacciones)."},
    {"name": "metodos_pago / flg_tarjeta_credito / flg_transferencia / etc. (trip1)", "group": "A", "source": "mkt_users_fact_payments + dim_payments", "usable_model": True, "note": "Cobertura ~97.5%; un 0 en flags especificos puede ser 'sin evidencia' mas que 'no usado' -- ver disclaimer cobertura Payments."},
    {"name": "gross_bookings_usd / net_revenues_usd / cost_usd / fee_net_usd (trip1, sumado por transaction_code)", "group": "A", "source": "mkt_users_fact_transactions", "usable_model": True, "note": "Cobertura completa 2020+. Existen valores negativos (refunds/ajustes, <1%) y ceros (~0.07%)."},
    {"name": "margin_variable_usd / npv_usd (trip1)", "group": "A", "source": "mkt_users_fact_transactions", "usable_model": "solo cohortes 2020+", "note": "100% NULL en 2019 (no existia el calculo). Excluir 2019 de cualquier analisis de margen/NPV."},
    {"name": "eventos_directo/seo/meta/crm/otros, eventos_path_total (trip1)", "group": "A", "source": "bi_mkt_fact_attributed_sales (model_id=33)", "usable_model": "solo cohortes 2021+", "note": "0% de cobertura en 2019-2020 (el modelo de atribucion no existia todavia). Es el path de ESA compra, no historial de exposicion del usuario."},
    {"name": "first_click / last_click datetime y event_type (trip1)", "group": "A", "source": "bi_mkt_fact_attributed_sales (model_id=33)", "usable_model": "descriptivo, cohortes 2021+ (no incluido en el modelo)", "note": "Mismo patron de cobertura que eventos_*. Se usa en el dashboard (seccion Path de medios) reclasificando event_type con la misma taxonomia Directo/CRM/SEM-SEO-KWBrand/Metabuscadores/Otros: CRM es el canal con mayor recompra asociada tanto de first-click como de last-click (~26.8%), Metabuscadores el menor (~16%). Los journeys con first y last click de canal distinto (multi-touch) recompran mas (24.8%) que los de un solo canal (21.6%). No se uso como feature del modelo por el mismo riesgo de confusion con cohort_year que eventos_*."},
    {"name": "flg_app_90d_antes_trip1 / visitas_app_90d_antes_trip1", "group": "A", "source": "mkt_users_fact_visits (App)", "usable_model": True, "note": "Incidencia creciente 2019->2025 (18%->57%): correlaciona con adopcion de la app en el tiempo, no solo con el usuario. SIEMPRE controlar por cohort_year."},
    {"name": "ultima_visita_app_antes_trip1", "group": "A", "source": "mkt_users_fact_visits (App)", "usable_model": True, "note": "Se puede derivar dias desde ultima visita a trip1."},

    # ---- Grupo A: variables nuevas incorporadas 2026-09-21 (perfil de usuario + caracteristicas del viaje) ----
    # No hay SQL/documentacion actualizada para estas variables (a diferencia del resto, que viene del
    # pipeline_rebuy_completo...sql). Se investigaron empiricamente: se verifico que income/birth_year/
    # nationality/antiguedad_usuario_dias_al_trip1/ciudad_residencia son constantes entre TODAS las filas de
    # nro_trip=1 de un mismo usuario (grano transaccion, no hay inconsistencia dentro de trip1), pero
    # SI cambian entre la fila de trip1 y la de trip2 del mismo usuario (60-72% de los casos difieren,
    # incluso birth_year) -> son snapshots que se recalculan por fila, probablemente contra una dimension de
    # perfil que se actualiza con el tiempo, no un valor verdaderamente fijo. Tomar SIEMPRE el valor de la
    # fila de trip1 (que es lo que hace este pipeline) es seguro para evitar leakage, pero la logica exacta
    # de como se calculo ese snapshot no esta confirmada -> pendiente de validar con el equipo de datos.
    {"name": "tipo_viaje (Nac/Int)", "group": "A", "source": "sin documentar (nuevo)", "usable_model": True,
     "note": "0% NULL. 99.2% consistente dentro de las transacciones de un mismo trip1 (se toma la de la transaccion mas temprana)."},
    {"name": "edad_aprox_primer_trip / rango_edad_primer_trip / birth_year", "group": "A", "source": "sin documentar (nuevo)", "usable_model": True,
     "note": "~27% NULL en birth_year. PENDIENTE: el valor difiere entre la fila de trip1 y trip2 del mismo usuario en ~68% de los casos (incluso birth_year, que no deberia cambiar) -> parece ser un snapshot recalculado, no un dato fijo. Se usa el valor de la fila de trip1."},
    {"name": "income", "group": "A", "source": "sin documentar (nuevo)", "usable_model": True,
     "note": "Categorico (Unknown/Low/Medium/High). ~9% NULL. Mismo caveat de snapshot que birth_year/nationality."},
    {"name": "nationality / pais_residencia / estado_residencia / ciudad_residencia", "group": "A", "source": "sin documentar (nuevo)", "usable_model": "nationality y pais_residencia si; ciudad muy alta cardinalidad, solo descriptivo",
     "note": "nationality ~30% NULL, ciudad_residencia ~34% NULL. Distinto de 'pais' (pais de la transaccion/viaje) -> permite separar de donde es el usuario de a donde viajo. Mismo caveat de snapshot."},
    {"name": "antiguedad_usuario_dias_al_trip1", "group": "A", "source": "sin documentar (nuevo)", "usable_model": True,
     "note": "~0.3% NULL, muy buena cobertura. Por nombre esta ancaldo a trip1, pero igualmente difiere entre fila trip1/trip2 en ~72% de los casos -> mismo caveat de snapshot que el resto de estas variables nuevas. Se usa el valor de la fila de trip1."},
    {"name": "geo_ultima_visita_ciudad/pais, geo_visita_frecuente_ciudad/pais, geo_ultima_transaccion_ciudad/pais", "group": "A", "source": "sin documentar (nuevo)", "usable_model": "descriptivo, alta cardinalidad para modelo",
     "note": "Verificado que son snapshots que avanzan con el tiempo (difieren 71-72% entre fila trip1 y trip2 del mismo usuario) -> tomar SIEMPRE el valor de la fila de trip1 es seguro (representa el estado a esa fecha), nunca mezclar con la fila de trip2."},
    {"name": "trip_checkin / trip_checkout / duracion_viaje_dias / bucket_duracion_viaje", "group": "A", "source": "sin documentar (nuevo)", "usable_model": True,
     "note": "0% NULL. 99.85% consistente dentro de las transacciones de un mismo trip1."},
    {"name": "dias_anticipacion_compra_checkin / bucket_anticipacion_compra", "group": "A", "source": "sin documentar (nuevo)", "usable_model": True,
     "note": "0% NULL, pero SI varia entre transacciones del mismo trip1 (~10.4% de los trips tienen anticipacion distinta segun la transaccion, ej. vuelo comprado con anticipacion y un seguro agregado despues) -> se toma la anticipacion de la transaccion mas temprana de trip1 (la reserva principal)."},
    {"name": "dias_entre_trip_1_y_2", "group": "C", "source": "sin documentar (nuevo)", "usable_model": False,
     "note": "Redundante con dias_a_recompra (calculado independientemente en este pipeline a partir de fecha_primer_trip/fecha_segundo_trip). Solo existe si ya hubo trip2 -> leakage directo, nunca se usa como feature."},

    # ---- Grupo B: post trip1, ventana controlable ----
    {"name": "flg_app_90d_post_trip1 / visitas_app_90d_post_trip1", "group": "B", "source": "mkt_users_fact_visits (App)", "usable_model": "solo subset no contaminado",
     "note": "CONTAMINADO para 31.5% de los recompradores (los que recompran <=90 dias): la ventana no se corta en fecha_segundo_trip. Se marca flg_contaminado_90d y se usa solo el subset limpio para el modelo/robustness check. No hay datos de visita individuales en el export para reconstruir una ventana exacta min(90d, trip2)."},
    {"name": "customer service (todas las variables cs_*)", "group": "D", "source": "as_omnichannel_fact_customer_experience", "usable_model": False,
     "note": "Sin timestamp de la interaccion en el export: no se puede saber si ocurrio antes o despues de trip2. Ademas cobertura estructuralmente distinta en el tiempo (~0% hasta 2023, 4.6-6.5% desde 2024). Se reporta solo como descriptivo, restringido a cohortes 2024+, nunca como feature predictiva."},

    # ---- Grupo C: leakage directo (dependen de trip2) ----
    {"name": "cantidad_visitas_entre_trips / cantidad_searches_entre_trips", "group": "C", "source": "mkt_users_fact_visits", "usable_model": False,
     "note": "Ventana termina exactamente en fecha_segundo_trip -> solo existe para quien ya recompro. Util para analisis descriptivo 'entre recompradores', nunca como feature de prediccion de recompra."},
    {"name": "flg_app_entre_trips / visitas_app_entre_trips / ultima_visita_app_antes_trip2", "group": "C", "source": "mkt_users_fact_visits (App)", "usable_model": False, "note": "Mismo problema: solo definido para quien ya tuvo trip2."},
    {"name": "plataforma_trip_2 / canales_compra_trip_2 / productos_trip_2", "group": "C", "source": "trip2", "usable_model": False, "note": "Es literalmente informacion del evento objetivo."},
    {"name": "flg_mismo_producto_trip_1_2", "group": "C", "source": "productos trip1 vs trip2", "usable_model": False, "note": "Solo puede calcularse si trip2 ya ocurrio."},
    {"name": "economics/loyalty/payments/cupon/CS/path de medios de trip2 (nro_trip=2)", "group": "C", "source": "transaction_code de trip2", "usable_model": False, "note": "Es informacion de la transaccion que define el target."},

    # ---- CRM historico (no incorporado) ----
    {"name": "eventos_crm (dentro de eventos_path_total)", "group": "D", "source": "bi_mkt_fact_attributed_sales", "usable_model": "descriptivo, con cuidado",
     "note": "Es el path de ATRIBUCION de la compra, no el historial de envios/opens/clicks de CRM. La documentacion indica cobertura de mkt_users_fact_comms todavia sin cerrar -> no se construyen conclusiones fuertes de CRM historico en este entregable."},
]


def as_markdown_table():
    header = "| Variable | Grupo | Fuente | Usable en modelo | Nota |\n|---|---|---|---|---|\n"
    rows = []
    for v in VARIABLES:
        rows.append(f"| {v['name']} | {v['group']} | {v['source']} | {v['usable_model']} | {v['note']} |")
    return header + "\n".join(rows)


if __name__ == "__main__":
    print(as_markdown_table())

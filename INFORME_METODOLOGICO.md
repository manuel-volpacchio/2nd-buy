# Informe metodológico — Análisis de recompra (REBUY) v2

Fecha: 2026-09-21
Fuente: `tmp.rebuy_final` (ver `pipeline_rebuy_completo_corregido_ordenado_sin_lineas_vacias.sql` y `resumen_pipeline_rebuy.pdf` adjuntos al proyecto), exportada mensualmente a `E:\Soporte\Reporting\Rebuy\historico\rebuy_final_YYYY_MM.csv`.

## 1. Universo y granularidad

El universo son usuarios (`social_id`) de Despegar B2C con transacciones y trips **confirmados**, cuyo primer y (si existe) segundo trip fueron identificados ordenando los trips por fecha. Reglas de inclusión del pipeline SQL:

- Usuarios con un solo trip: se mantienen siempre.
- Usuarios con segundo trip: se mantienen **solo si el segundo trip ocurre dentro de los 36 meses** posteriores al primero. Si el segundo trip observado ocurre después de 36 meses, **el usuario queda excluido de toda la tabla** (no se lo reclasifica como "1 trip"). Esto es importante: la ausencia de un usuario en la tabla no siempre significa "no tenemos datos de él", puede significar "tuvo una recompra tardía y fue excluido por diseño".

**Grano de `tmp.rebuy_final`**: `social_id + nro_trip + trip_id + transaction_code + producto`. Una misma transacción puede tener más de una fila si tiene más de un producto. Verificado empíricamente sobre el export completo (21.7M filas):

- 17.622.969 `transaction_code` distintos, promedio 1,23 filas por transacción, máximo 12.
- 11.676.533 `social_id` distintos.
- Se confirmó que **economics, cupón, loyalty, payments y Customer Service son 100% constantes dentro de un mismo `transaction_code`** (0 inconsistencias detectadas), y que **App y actividad-entre-trips son 100% constantes dentro de un mismo `social_id`** (0 inconsistencias). Esto valida que deduplicar por esas claves antes de agregar es seguro y no introduce sesgo.

### Pipeline de construcción de la vista de modelado

1. `01_build_base_tables.py`: deduplica el CSV crudo a `tx_level` (1 fila por `transaction_code`) y `user_level` (1 fila por `social_id`), tomando `MAX`/`ARG_MIN` según corresponda (validado que no hay inconsistencias, ver arriba).
2. `02_build_modeling_view.py`: agrega `tx_level` (solo `nro_trip=1`) a nivel usuario — **sumando** economics/eventos entre las transacciones distintas de trip1 (aditivo, correcto) y tomando **OR** para flags — y lo une con `user_level`. Calcula los targets multi-horizonte. Aplica la clasificación de variables por grupo de leakage (`variable_dictionary.py`).

**Nota de calidad**: 3.427 usuarios (0,03%) no tienen fila de `nro_trip=1` en `tx_level` — se verificó que el 100% de ellos tiene `rebuy_ever=1`. La hipótesis más probable es que su transacción de trip1 se perdió por errores de parseo del CSV (campos con comas sin escapar, ej. nombres de banco concatenados) que `ignore_errors=true` descarta silenciosamente. Se excluyeron de todos los análisis descriptivos y del modelo. El efecto sobre las conclusiones agregadas es despreciable (0,03% del universo) pero se documenta por transparencia.

## 2. Definición del target y manejo de censura

Se calcularon 4 horizontes: **6, 12, 24 y 36 meses**, cada uno con su propio flag de elegibilidad:

```
eligible_Nm = fecha_primer_trip <= (fecha_máxima_de_datos - N meses)
rebuy_Nm    = existe fecha_segundo_trip Y fecha_segundo_trip <= fecha_primer_trip + N meses
```

La tasa de recompra a N meses se calcula **solo** sobre `eligible_Nm = True`. Esto evita mezclar cohortes que todavía no tuvieron tiempo de cumplir la ventana (censuradas) con cohortes maduras — un usuario de julio 2026 no puede compararse con uno de enero 2019 en el horizonte de 12 meses si al primero todavía no le pasaron los 12 meses.

Fecha máxima de datos observada: **2026-09-14**. Resultados por horizonte (universo elegible correspondiente):

| Horizonte | Usuarios elegibles | Recompraron | Tasa |
|---|---:|---:|---:|
| 6 meses | 10.512.723 | 1.491.427 | 14,2% |
| 12 meses | 9.310.116 | 1.986.865 | 21,3% |
| 24 meses | 7.520.250 | 2.156.199 | 28,7% |
| 36 meses | 6.012.868 | 1.964.297 | 32,7% |

Se usó aritmética de **mes calendario** (no días aproximados) para ser consistente con la regla de 36 meses del propio pipeline SQL.

### Censura administrativa a 36 meses (survival analysis)

Como el pipeline ya excluye del universo a cualquier usuario cuyo segundo trip ocurrió más allá de 36 meses, ningún sujeto de esta tabla puede tener, por construcción, un evento observable más allá de esa ventana. Por eso el análisis de supervivencia (Kaplan-Meier) trunca administrativamente a 1096 días (36 meses):

```
T = dias_a_recompra                                  si recompró dentro de 36 meses
T = min(días observados desde trip1, 1096)           si no recompró (censurado)
E = 1 si recompró dentro de 36 meses, 0 si censurado
```

## 3. Clasificación de variables y prevención de target leakage

Ver `diccionario_variables.md` para el detalle completo. Resumen de grupos:

- **Grupo A (seguras, disponibles al momento de trip1)**: país, producto, plataforma/canal de trip1, flight class, cupón, loyalty (tier/puntos) de trip1, payments de trip1, economics de trip1, path de medios y first/last click **de trip1**, App en los 90 días **antes** de trip1.
- **Grupo B (post-trip1, ventana controlable)**: `flg_app_90d_post_trip1` / `visitas_app_90d_post_trip1`. **Contaminada para el 31,5% de los recompradores** (los que recompraron dentro de esos 90 días): la ventana del pipeline no se corta en `fecha_segundo_trip`, así que puede incluir actividad posterior a la recompra. No se reconstruyó una versión exacta porque el export no tiene datos de visita a nivel evento individual (solo el agregado a 90 días) — queda marcada como limitación y pendiente para una v2 del SQL fuente. No se usó en el modelo principal.
- **Grupo C (leakage directo, nunca usadas como feature)**: `cantidad_visitas/searches_entre_trips`, `flg_app_entre_trips`, `plataforma_trip_2`, `canales_compra_trip_2`, `productos_trip_2`, `flg_mismo_producto_trip_1_2`, y cualquier variable de la transacción de `nro_trip=2` (son literalmente parte del evento que se quiere predecir).
- **Grupo D (descriptivas, cobertura/temporalidad no resuelta)**: Customer Service (sin timestamp de la interacción → no se puede establecer si fue antes o después de una eventual recompra; además cobertura ~0% hasta 2023 y 4,6-6,5% desde 2024) y CRM histórico (la documentación del pipeline indica que la cobertura de `mkt_users_fact_comms` todavía está en revisión; `eventos_crm` es del path de atribución de la compra, no el historial de comunicaciones).

## 4. Cambios estructurales de cobertura detectados (auditoría)

| Fuente | Hallazgo |
|---|---|
| Path de medios / first-last click (`bi_mkt_fact_attributed_sales`, model_id=33) | 0% de cobertura en 2019-2020, ~97-98% desde 2021. Todo corte por canal de atribución se restringe a cohortes 2021+. |
| Customer Service (`as_omnichannel_fact_customer_experience`) | ~0,003%-0,09% de transacciones con interacción hasta 2023, salta a 4,6%-6,5% desde 2024. Cortes de CS restringidos a cohortes 2024+. |
| Margin/NPV (`mkt_users_fact_transactions`) | 100% NULL en 2019, ~0% NULL desde 2020. Excluir 2019 de análisis de margen/NPV. |
| Payments (`mkt_users_fact_payments` + `dim_payments`) | Cobertura estable ~96,5%-98,6% en todo el período — sin cambio estructural relevante. |
| Uso de App antes de trip1 | Incidencia creciente de 18% (2019) a 57% (2025) — probablemente adopción real de la app, pero no se puede descartar mejora de instrumentación. Se controla por `cohort_year` en el modelo. |
| Uso de puntos loyalty | Incidencia de 0,02% (2019) a 9% (2026) — crecimiento muy grande, compatible con expansión real del programa de loyalty pero no verificable de forma independiente con este export. |

## 5. Metodología estadística

- **Horizonte estándar = 18 meses**: a pedido del equipo (Matías Grussi, 2026-09-21), se adoptó 18 meses como la ventana estándar de "retention" para viajes (en vez de 12), ya que muchos usuarios viajan ~1 vez al año y una ventana de 12 meses podía subestimar a quienes recompran poco después del año. Todos los cortes descriptivos, el panel de segmentos y el target del modelo usan 18m por default; 6/12/24/36m siguen disponibles para comparar (ver tabla de cohortes).
- **Descriptivos**: todos los cortes categóricos/bins se calcularon exclusivamente sobre `eligible_18m=True`, con un mínimo de 300 usuarios por segmento para evitar conclusiones sobre bases chicas.
- **Cohortes**: agregación por año/mes de `fecha_primer_trip`, con la tasa de cada horizonte calculada solo sobre las cohortes que ya cumplieron ese horizonte.
- **Survival analysis**: Kaplan-Meier (librería `lifelines`) general y por subgrupo (país, App, producto, plataforma, loyalty), con test de log-rank para significancia de las diferencias entre curvas.
- **Modelo multivariado**: población = `eligible_18m=True` y con datos de trip1 válidos. Target = `rebuy_18m`. Split **temporal, no aleatorio**: train = cohortes con `fecha_primer_trip` anterior a 2024-08 (~80%), test = cohortes 2024-08 en adelante hasta la última cohorte madura (~20%, out-of-time). Solo features de Grupo A, ahora incluyendo tipo de viaje, rango de edad, nivel de ingreso, anticipación de compra, duración del viaje y antigüedad de cuenta (ver sección 7).
  - **Regresión logística**: sklearn con regularización L2 (se intentó `statsmodels.Logit` sin penalizar, pero produjo una matriz Hessiana singular por cuasi-separación perfecta en categorías de baja frecuencia — ej. países con pocos cientos de usuarios). Intervalos de confianza al 95% y p-valores aproximados calculados por **bootstrap** (100 remuestreos de 150.000 filas).
  - **Gradient Boosting**: `HistGradientBoostingClassifier` (sklearn) con soporte nativo de variables categóricas, `early_stopping` habilitado.
  - **Métricas**: ROC-AUC, PR-AUC, calibración (predicho vs observado por bins), lift por decil de score — todas calculadas sobre el test set out-of-time, nunca sobre train.
  - **Interpretabilidad**: para el GBM se calculó **permutation importance** (no SHAP): la versión de `shap` disponible no soporta el manejo nativo de categóricas de `HistGradientBoostingClassifier` (intenta castear a float y falla). Permutation importance es una alternativa válida y model-agnostic (mide cuánto empeora el ROC-AUC al permutar aleatoriamente cada columna).

## 7. Variables nuevas incorporadas (2026-09-21): perfil de usuario y características del viaje

El equipo de datos sumó ~27 columnas nuevas a `tmp.rebuy_final`: demográficas (`birth_year`, `edad_aprox_primer_trip`, `rango_edad_primer_trip`, `income`, `nationality`, `pais_residencia`, `estado_residencia`, `ciudad_residencia`), antigüedad de cuenta (`antiguedad_usuario_dias_al_trip1`), geolocalización (`geo_ultima_visita_*`, `geo_visita_frecuente_*`, `geo_ultima_transaccion_*`) y características del viaje (`tipo_viaje`, `trip_checkin/checkout`, `dias_anticipacion_compra_checkin`, `duracion_viaje_dias`, `bucket_anticipacion_compra`, `bucket_duracion_viaje`).

**A diferencia del resto de la tabla, no hay SQL ni documentación formal para estas variables.** Se investigaron empíricamente antes de incorporarlas:

- **Grano**: `tipo_viaje`, `duracion_viaje_dias` y `trip_checkin/checkout` son ~99.9% constantes entre las transacciones de un mismo trip1 → se toma la de la transacción más temprana como representativa. `dias_anticipacion_compra_checkin` **sí varía** entre transacciones del mismo trip1 en un 10,4% de los casos (ej. el vuelo se compra con anticipación y un seguro se agrega después) → se toma también la de la transacción más temprana (la reserva principal).
- **Caveat importante — snapshots que cambian con el tiempo**: se verificó que `income`, `birth_year`, `nationality` y `antiguedad_usuario_dias_al_trip1` son constantes entre todas las transacciones de la fila de trip1 de un usuario, pero **difieren entre la fila de trip1 y la fila de trip2 del mismo usuario en 60-72% de los casos** — incluso `birth_year`, que no debería cambiar. Esto sugiere que son snapshots recalculados por fila contra alguna dimensión de perfil que se actualiza en el tiempo, no valores fijos. Usar siempre el valor de la fila de trip1 (que es lo que hace este pipeline) es seguro para evitar leakage, pero la lógica exacta de cómo se generó ese snapshot **queda pendiente de confirmar con el equipo de datos**.
- **Cobertura**: `dias_anticipacion_compra_checkin` y `duracion_viaje_dias` 0% NULL; `antiguedad_usuario_dias_al_trip1` ~0,3% NULL; `income` ~9% NULL; `birth_year`/`nationality` ~27-30% NULL; `ciudad_residencia` ~34% NULL.
- **Uso en el modelo**: se incorporaron `tipo_viaje`, `rango_edad_primer_trip`, `income`, `bucket_anticipacion_compra`, `bucket_duracion_viaje` y `antiguedad_usuario_dias_al_trip1` como features Grupo A. `nationality`/`pais_residencia`/`ciudad_residencia`/campos geo quedaron descriptivos únicamente (redundancia con `pais` o cardinalidad muy alta).
- **`dias_entre_trip_1_y_2`** es Grupo C (leakage): redundante con `dias_a_recompra`, solo existe si ya hubo trip2.

## 8. Limitaciones generales

- Todo lo reportado es **asociación observacional**, no causalidad, salvo que se indique explícitamente un diseño experimental.
- La tabla es una vista analítica, no un dataset de entrenamiento listo — esta es la primera vez que se fija una fecha de corte uniforme y se separan features seguras de features con leakage; antes de este trabajo no existía esa distinción documentada.
- El poder predictivo del modelo (ROC-AUC ~0,58-0,59 out-of-time) es moderado: el comportamiento en trip1 por sí solo tiene una capacidad limitada de anticipar la recompra. **Lectura del ROC-AUC**: es la probabilidad de que el modelo ordene correctamente un par (usuario que recompró, usuario que no) elegido al azar. Escala de referencia: 0,50 = azar puro; 0,60-0,70 = señal moderada; 0,70-0,80 = buena; 0,80+ = muy buena/excelente (poco común en predicción de comportamiento humano). Nuestro ~0,59 cae en "señal moderada, apenas por encima del azar" — esto es en sí mismo un hallazgo relevante — sugiere que la recompra depende en buena medida de factores no capturados en esta tabla (experiencia del viaje, factores externos, competencia).

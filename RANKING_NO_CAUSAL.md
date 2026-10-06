# Ranking NO causal de variables asociadas a recompra

**Importante**: este ranking describe asociaciones observadas en un modelo multivariado (que controla por las demás variables entre sí), no relaciones de causa-efecto. Ver `INFORME_METODOLOGICO.md` para el detalle de cómo se construyó cada modelo y `HIPOTESIS_EXPERIMENTOS.md` para las hipótesis causales a validar.

**Actualizado 2026-09-21** tras incorporar variables demográficas y de características del viaje (edad, ingreso, tipo de viaje, anticipación de compra, duración del viaje, antigüedad de cuenta) y cambiar el horizonte estándar de 12 a **18 meses** (pedido de Matías Grussi).

Se reportan dos rankings complementarios porque miden cosas distintas:

- **Odds ratio (regresión logística)**: cuánto cambian las chances de recompra para alguien que tiene esa característica, controlando por el resto. Es sensible al *tamaño del efecto*, incluso en variables poco frecuentes.
- **Permutation importance (Gradient Boosting)**: cuánto empeora la capacidad predictiva global del modelo si se "rompe" esa variable. Es sensible a cuánta gente tiene esa característica — una variable rara con efecto enorme (ej. loyalty) puede importar poco a nivel población aunque tenga un odds ratio alto.

Ambos modelos se evaluaron **fuera de tiempo** (entrenados con cohortes hasta 2024-07, evaluados en cohortes 2024-08 en adelante) y usan **solo variables de Grupo A** (disponibles al momento de la 1ª compra, sin leakage — ver `diccionario_variables.md`). Target: `rebuy_18m`.

## Mejora del modelo con las variables nuevas

| | ROC-AUC (GBM) | ROC-AUC (Logística) | PR-AUC (GBM) |
|---|---:|---:|---:|
| Antes (sin demográficas, target 12m) | 0,589 | 0,579 | 0,273 |
| Ahora (con demográficas, target 18m) | **0,693** | **0,636** | **0,454** |

Salto grande: de "señal muy débil" a "señal moderada". Las variables de edad e ingreso explican buena parte de esa mejora — ver el matiz importante abajo.

## Ranking por Permutation Importance (Gradient Boosting) — quién manda ahora

| Variable | Importancia (caída de ROC-AUC) |
|---|---:|
| **Rango de edad al momento de trip1** | **0,1092** |
| **Nivel de ingreso estimado** | **0,0498** |
| Producto (purchase_type) | 0,0127 |
| Nº de transacciones en trip1 | 0,0127 |
| Antigüedad de cuenta al momento de trip1 | 0,0123 |
| Flight class | 0,0074 |
| Visitas App antes de trip1 | 0,0069 |
| País | 0,0049 |
| Pagó con tarjeta de crédito | 0,0032 |
| Usó puntos loyalty | 0,0030 |
| Duración del viaje | 0,0020 |
| Anticipación de compra | 0,0020 |
| Gasto (log gross bookings) | 0,0019 |
| Pagó con transferencia | 0,0013 |
| Plataforma principal | 0,0010 |
| Tipo de viaje (nac/int) | 0,0002 |
| Año de cohorte | 0,0000 |

**⚠️ Matiz crítico sobre edad e ingreso — no leer esto como "la edad predice la recompra" sin más:**

Al desagregar el odds ratio por categoría, la categoría **"Sin dato" de edad tiene OR=0,25** y **"Unknown"/nulo de ingreso tiene OR=0,46/0,16** — muy por debajo de cualquier valor real conocido. Es decir, una parte importante de por qué "edad" e "ingreso" dominan el modelo es que **tener el dato informado en sí mismo ya es una señal fuerte** (posiblemente correlacionado con perfiles más completos/verificados/antiguos), no solo el valor demográfico. Dicho esto, **también hay un gradiente real entre quienes SÍ tienen el dato**: 25-34 años recompra 38,8% vs 65+ solo 20,5% — la edad importa incluso controlando por si el dato existe. Recomendación: tratar esta variable con cautela en decisiones de negocio hasta separar ambos efectos (completitud de perfil vs. edad real), y preguntarle a Data cómo/cuándo se completa este dato.

## Ranking por Odds Ratio (categorías con dato conocido, asociación positiva)

| Variable | Odds Ratio | IC95% |
|---|---:|---|
| Usó puntos loyalty en trip1 | 2,26 | (1,57 – 2,53) |
| Canal "Beneficio Despegar" | 1,85 | (1,00 – 2,88) |
| Producto: Bundles | 1,77 | (1,23 – 2,78) |
| Producto: Carrito (multi-producto) | 1,56 | (1,49 – 1,93) |
| Producto: Traslados | 1,53 | (1,31 – 1,89) |
| Producto: Vuelos | 1,46 | (1,41 – 1,81) |
| País Colombia | 1,35 | (1,25 – 1,38) |
| País Brasil | 1,26 | (1,19 – 1,29) |
| Pagó con transferencia | 1,23 | (1,16 – 1,30) |

## Ranking por Odds Ratio (asociación negativa, excluyendo categorías "sin dato")

| Variable | Odds Ratio | IC95% |
|---|---:|---|
| Rango de edad 65+ | 0,57 | (0,54 – 0,66) |
| Nivel de ingreso "Low" | 0,65 | (0,62 – 0,68) |
| País Costa Rica | 0,66 | (0,47 – 0,86) |
| Canal Call Center | 0,67 | (0,44 – 0,73) |

## Lectura cruzada

- **Nº de transacciones en trip1** sigue siendo de las variables más robustas y "útiles" a nivel de todo el modelo (importancia 0,0127, cae poco respecto de la versión anterior) — es común (no depende de que falte un dato) y con efecto consistente: 1 transacción → 24,3% de recompra a 18m, 2 → 34,0%, 3+ → 42,3%.
- **Antigüedad de cuenta** (variable nueva) entra fuerte (0,0123) con una relación no lineal: peor en cuentas creadas el mismo día del viaje (20,9%), pico en cuentas de 31-180 días (33,1%), leve caída en cuentas muy viejas (3+ años: 30,4%).
- **El año de cohorte sigue sin aportar nada al modelo multivariado** (0,0000) — su efecto univariado se explica indirectamente por las demás variables.
- El **poder predictivo global mejoró de moderado-débil a moderado** (ROC-AUC 0,693 fuera de tiempo) gracias a las variables demográficas, pero con el matiz de completitud de datos explicado arriba.

## Variables excluidas de este ranking (no usables como predictoras — ver diccionario de variables)

`cantidad_visitas/searches_entre_trips`, `flg_app_entre_trips`, `plataforma_trip_2`, `canales_compra_trip_2`, `productos_trip_2`, `flg_mismo_producto_trip_1_2`, `dias_entre_trip_1_y_2`, toda variable de la transacción de `nro_trip=2`, `flg_app_90d_post_trip1` (contaminada en 31,5% de los recompradores), Customer Service (sin timestamp de la interacción), CRM histórico (cobertura no cerrada), `nationality`/`pais_residencia`/`ciudad_residencia`/campos geo (descriptivos, redundancia con `pais` o cardinalidad muy alta).

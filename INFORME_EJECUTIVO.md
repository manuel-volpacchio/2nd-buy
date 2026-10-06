# Informe ejecutivo — Qué distingue a quien vuelve a comprar

**Pregunta de negocio**: ¿qué diferencia a los usuarios que hacen una 2ª compra de los que no, qué señales tempranas se asocian a mayor probabilidad de recompra, y qué vale la pena experimentar?

**Base**: 11,68M usuarios de primera compra en Despegar B2C, 2019-2026. Todo lo que sigue es **asociación observada**, no causalidad, salvo que se indique lo contrario.

## Los números base

- **Horizonte estándar: 18 meses** (cambiado de 12 a pedido del equipo, ya que muchos usuarios viajan ~1 vez al año). A 18 meses, **25,6%** de los usuarios recompra (medido solo sobre cohortes con 18 meses completos de exposición, para no subestimar por censura).
- La tasa sube a **28,7%** a 24 meses y **32,7%** a 36 meses — buena parte de la recompra "tardía" sigue llegando después del primer año y medio.
- Mediana de tiempo hasta la 2ª compra: **~193 días** (algo más de 6 meses) entre quienes recompran.

## Las señales más fuertes (por orden de magnitud del efecto observado)

1. **Loyalty (tier y uso de puntos) — la asociación más grande a nivel individual.** Usuarios que redimieron puntos en su 1ª compra y llegaron al tier más alto ("3-Global") muestran tasas de recompra de hasta ~70%, muy por encima del general. *Advertencia importante*: el tier se gana viajando/gastando más, así que buena parte de esto es que ya eran viajeros frecuentes — no se puede asumir que "subir a alguien de tier" por sí solo generaría ese efecto.
2. **Edad e ingreso — las variables más importantes para el modelo en su conjunto, con un matiz clave.** Se agregaron estas variables nuevas y mejoraron mucho la capacidad del modelo. Entre quienes SÍ tienen el dato, hay un gradiente real: 25-34 años recompra 38,8% vs. 65+ solo 20,5%; ingreso "Alto" 40,1% vs. "Bajo" 31,3%. **Pero** la categoría "sin dato" en ambas variables tiene tasas mucho más bajas que cualquier valor real conocido — sugiere que buena parte de lo que el modelo está captando es "¿tenemos un perfil completo de este usuario?", no solo la edad/ingreso en sí. Tratar con cautela antes de accionar.
3. **Reservar más de una transacción dentro de la 1ª compra.** 1 transacción → 24,3% de recompra a 18m, 2 → 34,0%, 3+ → 42,3%. Es una de las señales más robustas y menos dependiente de datos faltantes.
4. **Antigüedad de la cuenta al momento de la 1ª compra — relación en forma de U invertida.** Quienes se registraron el mismo día de su compra recompran menos (20,9%); la recompra sube fuerte con algo de antigüedad (pico en 31-180 días: 33,1%) y baja levemente en cuentas muy viejas (3+ años: 30,4%).
5. **Uso de la App antes de la 1ª compra — dosis-respuesta clara.** A más visitas a la App en los 90 días previos a comprar, mayor la recompra observada, de forma escalonada y consistente.
6. **El gasto de la 1ª compra tiene forma de "U", no es lineal.** Tanto compras muy chicas como muy grandes recompran más que el rango medio — no es cierto que "a mayor gasto, mayor lealtad" de forma simple.
7. **El canal de adquisición importa**: dentro del path de atribución de la 1ª compra (solo medible en cohortes 2021+), Metabuscadores muestra la menor recompra asociada y CRM la mayor — tanto mirando el canal dominante del path completo como el primer y el último click (first/last touch) por separado. Los usuarios cuyo primer y último click fueron de **canales distintos** (journey multi-touch) recompran más que los de un solo canal de punta a punta.

## Lo que NO muestra una asociación clara (y por qué importa reportarlo)

- **Customer Service**: tener o no una interacción de soporte en la 1ª compra no muestra diferencia relevante en recompra, ni tampoco la satisfacción declarada. Con una salvedad importante: el dato no tiene timestamp de la interacción, así que esto es puramente descriptivo — no se puede usar todavía para decisiones de negocio sobre CS.
- **Cupón en la 1ª compra**: no se asocia a mayor recompra (si acaso, levemente menor) — consistente con un perfil más sensible a precio que a lealtad.
- **Medio de pago (tarjeta de crédito vs. otros)**: diferencias marginales, no es un driver relevante por sí solo.

## Qué dice el modelo cuando se mira todo junto

Se entrenó un modelo multivariado (regresión logística + Gradient Boosting) usando **solo información disponible al momento de la 1ª compra** (nunca datos de la 2ª compra ni actividad posterior que dependa de ella — ver informe metodológico), evaluado sobre cohortes que el modelo nunca vio en el entrenamiento (validación fuera de tiempo).

- El modelo logra un poder predictivo **moderado (ROC-AUC 0,693)**, una mejora importante frente a la primera versión sin las variables demográficas (0,589). **Cómo leer este número**: el ROC-AUC es la probabilidad de que, tomando al azar un usuario que recompró y uno que no, el modelo le haya puesto un puntaje más alto al que sí recompró. 0,50 = tirar una moneda (el modelo no aporta nada), 1,00 = predicción perfecta. Nuestro 0,693 significa que el modelo acierta ese orden en ~69% de los casos — hay señal real y ahora más sustancial, pero el comportamiento/perfil en la 1ª compra por sí solo sigue lejos de determinar si alguien va a recomprar.
- Controlando todas las variables entre sí, **edad e ingreso pasan a ser las variables más importantes del modelo** (con el matiz de completitud de datos explicado arriba), seguidas de nº de transacciones en trip1, antigüedad de cuenta y uso de App — todas se mantienen como asociaciones consistentes, no solo artefactos de estar correlacionadas con otra variable más fuerte.

## Qué vale la pena experimentar

1. **Pedirle a Data que separe "completitud de perfil" de "valor demográfico real"** en edad/ingreso — hoy no podemos saber cuánto del efecto es uno u otro, y es la variable más importante del modelo.
2. **A/B test de activación de App post-1ª-compra** (notificaciones, contenido personalizado) — para separar causalidad de correlación en la señal de App.
3. **Acceso anticipado a beneficios de tier** para clientes nuevos de alto potencial, midiendo recompra incremental vs. un grupo control.
4. **Journeys diferenciados para adquisición vía metabuscadores** — hoy es el origen con menor recompra asociada.
5. **Pedir a Data el timestamp de las interacciones de Customer Service** antes de construir cualquier iniciativa de negocio sobre esa variable.
6. **Segmentar cualitativamente los extremos de gasto en la 1ª compra** (muy bajo / muy alto) para entender si son perfiles distintos y diseñar journeys específicos.
7. **Investigar la caída de recompra en cuentas creadas el mismo día del viaje** — ¿son usuarios de "guest checkout" o corporativos? Podría justificar un journey de activación de cuenta distinto.

Detalle completo, metodología, limitaciones y tabla de variables en `INFORME_METODOLOGICO.md`, `diccionario_variables.md` y el dashboard interactivo (`rebuy_dashboard.html`).

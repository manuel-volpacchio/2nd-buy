# Hipótesis y experimentos sugeridos

Cada ítem sigue el mismo formato: hallazgo → tamaño del segmento → magnitud observada → interpretación posible → riesgo de confounding → experimento sugerido → KPI a medir.

---

### 1. Engagement con la App post-1ª-compra

- **Hallazgo**: dosis-respuesta monótona entre visitas a la App en los 90 días antes de trip1 y recompra a 12 meses (18,98% sin uso → 30,4% con 16+ visitas).
- **Tamaño del segmento**: 3,19M usuarios (27%) usaron la App antes de su 1ª compra; 6,12M (52%) no.
- **Magnitud**: +7 a +11 puntos porcentuales de recompra según intensidad de uso.
- **Interpretación posible**: la App genera más engagement/hábito → más recompra. O bien: usuarios ya más propensos a viajar de nuevo también navegan más (selección, no causalidad).
- **Riesgo de confounding**: alto. La incidencia de uso de App creció de 18% (2019) a 57% (2025) — la señal cruda está mezclada con la adopción general de la app en el tiempo. El modelo multivariado controla por año de cohorte y la señal se mantiene, pero no es un experimento.
- **Experimento sugerido**: A/B de notificaciones/contenido personalizado en la App dirigido a usuarios recién convertidos, midiendo recompra incremental en el grupo tratado vs. control a 90/180 días.
- **KPI a medir**: tasa de recompra a 90/180 días, tiempo hasta 2ª compra, engagement en la App (sesiones/semana).

---

### 2. Loyalty (tier y uso de puntos)

- **Hallazgo**: usuarios que redimieron puntos en trip1 recompran a 35,9% (vs 21,2% quienes no); por tier, "3-Global" llega a ~71%, "2-Explorador" a ~51%, "1-Viajero" a ~24%.
- **Tamaño del segmento**: 56.819 usuarios usaron puntos en trip1 (0,6% del total elegible) — n chico en términos relativos pero robusto en términos absolutos.
- **Magnitud**: la asociación más grande de todo el análisis (+15 a +50 puntos porcentuales según tier).
- **Interpretación posible**: pertenecer a un tier alto refleja ya ser un viajero frecuente (el tier se gana viajando/gastando) — causalidad inversa muy probable, al menos parcialmente.
- **Riesgo de confounding**: muy alto (ver arriba). No se puede aislar sin un diseño experimental.
- **Experimento sugerido**: dar acceso anticipado a beneficios de un tier superior a un grupo de clientes nuevos de alto potencial (elegido por otras señales, no por historial de loyalty) y medir recompra incremental vs. grupo control sin ese acceso.
- **KPI a medir**: tasa de recompra a 12 meses, gasto promedio en la 2ª compra, tiempo hasta la 2ª compra.

---

### 3. Canal de atribución (Metabuscadores vs. CRM)

- **Hallazgo**: dentro del path de atribución de trip1 (cohortes 2021+), el canal dominante "Metabuscadores" está asociado a 15,2% de recompra, el más bajo de todos; "CRM" al 26,8%, el más alto.
- **Tamaño del segmento**: 339.882 usuarios con Metabuscadores como canal dominante; 811.324 con CRM.
- **Magnitud**: ~11,6 puntos porcentuales de diferencia.
- **Interpretación posible**: los usuarios que llegan comparando precios en metabuscadores son más price-driven y menos leales por naturaleza; los de CRM ya estaban en la base de contactos (podrían no ser adquisición "pura").
- **Riesgo de confounding**: alto — la composición de producto/país puede diferir fuertemente entre estos canales.
- **Experimento sugerido**: testear journeys de fidelización específicos (ej. primer email de bienvenida con incentivo a instalar la App o sumarse a loyalty) para usuarios adquiridos vía metabuscadores.
- **KPI a medir**: tasa de recompra a 12 meses del cohort tratado vs. histórico del mismo canal.

---

### 4. Extremos de gasto en la 1ª compra

- **Hallazgo**: relación en forma de U entre gross bookings de trip1 y recompra — tanto compras <100 USD (22,1%) como 2500+ USD (25,2%) recompran más que el rango medio 500-1000 USD (20,4%).
- **Tamaño del segmento**: 1,75M usuarios en el bucket <100 USD; 268K en el bucket 2500+ USD.
- **Magnitud**: ~2 a ~5 puntos porcentuales por encima del rango medio.
- **Interpretación posible**: dos poblaciones distintas en los extremos — compradores ocasionales de bajo compromiso (bus, hotel suelto) que repiten ese mismo tipo de compra chica seguido, vs. viajeros de alto valor ya fidelizados.
- **Riesgo de confounding**: medio-alto — mezcla con producto y país.
- **Experimento sugerido**: segmentación cualitativa de ambos extremos (encuestas o revisión de producto/país dominante) antes de diseñar cualquier journey específico.
- **KPI a medir**: no aplica experimento cuantitativo todavía — primero investigación exploratoria.

---

### 5. Reservar más de una transacción en la 1ª compra

- **Hallazgo**: 1 transacción → 20,2% de recompra; 2 → 28,3%; 3+ → 35,4%.
- **Tamaño del segmento**: 8,25M usuarios con 1 transacción; 813K con 2; 243K con 3+.
- **Magnitud**: hasta +15 puntos porcentuales.
- **Interpretación posible**: usuarios que ya interactúan más con la plataforma en su primera experiencia (compran ancillaries por separado, agregan servicios) son usuarios más comprometidos desde el inicio.
- **Riesgo de confounding**: medio — correlaciona con gasto total y con producto (Vuelos+Hoteles separados vs. un solo producto).
- **Experimento sugerido**: no es una variable accionable directamente (no se puede "forzar" a alguien a transaccionar más veces), pero sirve como señal de scoring/priorización para journeys de retención tempranos.
- **KPI a medir**: usar como feature de un modelo de propensión a recompra para priorizar a quién dirigir campañas de reactivación.

---

### 6. Customer Service (hallazgo nulo, reportado por transparencia)

- **Hallazgo**: sin diferencia relevante en recompra entre quienes tuvieron interacción de CS en trip1 y quienes no (21,0% vs 21,4%, cohortes 2024+), ni por satisfacción declarada.
- **Interpretación posible**: podría ser un efecto real (CS no mueve la aguja de recompra) o podría estar diluido por la falta de temporalidad (no se sabe si la interacción fue antes o después de una eventual 2ª compra).
- **Riesgo de confounding**: no resuelto — falta el timestamp de la interacción.
- **Acción sugerida**: no es un experimento todavía. Es un pedido a Data: incorporar timestamp de la interacción de CS al pipeline antes de sacar conclusiones de negocio.
- **KPI a medir**: pendiente de la mejora de datos.

---
source_id: "doi:10.3389/fnsys.2020.00019"
source_type: paper
title: "The Cerebro-Cerebellum as a Locus of Forward Model: A Review"
generated_at: 2026-05-30T21:57:10+00:00
---

- p.1 🧠 El cerebro-cerebelo como sustrato neural del modelo interno directo (forward model)

  - El cerebro-cerebelo, la expansión filogenéticamente más reciente del cerebelo, recibe entradas convergentes corticales, subcorticales y espinales y realiza la computación predictiva conocida como modelo interno directo,
  - El cerebelo emergió en la placa alar (parte sensorial) del tubo neural del rombencéfalo de vertebrados primitivos como mixinoideos y petromizontes, situándose idealmente como hub de integración sensorial,
  - La computación predictiva del modelo interno directo se propone como el principio algorítmico unificador de las funciones motoras, de aprendizaje motor y cognitivas del cerebelo,

- p.2 🔮 El cerebelo computa un algoritmo común sobre representaciones heterogéneas

  - En humanos el cerebelo contiene no menos del 80% de las neuronas del SNC en no más del 10% del volumen cerebral (Herculano-Houzel, 2009),
  - El cerebelo es homogéneo en su circuitería local ("cristalina") pero heterogéneo en su organización de entradas-salidas, por lo que su diversidad funcional se atribuye a la conectividad y un algoritmo común,
  - Los autores se preguntan "cómo computa el cerebelo" en lugar de "qué computa", analizando cómo transforma las fibras musgosas (MFs) en células del núcleo dentado (DNCs),
  - El modelo interno directo predice resultados de la auto-acción, permite control motor rápido y estable, integra predicción con feedback sensorial y posibilita la adaptación a entornos nuevos,

- p.2 ⏱️ El retardo de la realimentación sensorial obliga a una predicción interna

  - Las señales aferentes sensoriales sufren retardos temporales inevitables: las señales visuales llegan a V1 unos 30 ms y al córtex parietal unos 80 ms tras el estímulo (Schmolesky et al., 1998),
  - El factor dominante del retardo es la conducción nerviosa, que va de ~10 ms en una musaraña a ~100 ms en un elefante,
  - El control por realimentación basado en estados pasados produce movimientos oscilatorios e inestables si el retardo es del orden del constante de tiempo de la planta controlada,

- p.3 🎯 El modelo interno directo cumple tres roles en control y aprendizaje motor

  - Predice el estado futuro del cuerpo a partir del estado actual y la copia eferente, permitiendo realimentación interna para movimientos rápidos y estables,
  - El error de predicción (no el error de objetivo) es lo que impulsa la adaptación motora, según el experimento de rotación visuomotora de Mazzoni y Krakauer (2006),
  - El modelo de control óptimo de realimentación (OFC) integra modelo directo, filtro de Kalman y control por realimentación, optimizando una función de coste (error más coste de control),
  - Los tres roles clave son: predicción de estado para compensar el retardo, predicción para computar el error de predicción en el aprendizaje, y cálculo de las ganancias de Kalman y de realimentación,

- p.4 🧩 La estructura feedforward del circuito cerebeloso encaja con el modelo directo

  - El circuito cerebeloso presenta conectividad mayoritariamente feedforward de MFs a DN, con expansión de MFs a células granulares y compresión de MFs a DNCs,
  - En la hipótesis, el estado retardado y la señal de control corresponden a las MFs, y el estado predicho corresponde a los DNCs,
  - La evidencia previa (clínica, neuroimagen, estimulación no invasiva) muestra que las actividades predictivas se alteran al dañar el cerebelo (Nowak et al.; Miall et al., 2007) y que el aprendizaje motor se deteriora en pacientes cerebelosos (Martin et al., 1996; Tseng et al., 2007),

- p.4 ⚖️ La generación de salidas del DN se explica por desinhibición de las células de Purkinje

  - Comparando PCs y DNCs en monos durante movimientos de muñeca, la mayoría de PCs se suprimió antes del inicio del movimiento mientras los DNCs se activaron sin supresión previa, apoyando la desinhibición frente al rebote post-inhibitorio (Ishikawa et al., 2014),
  - La actividad de cada DNC se regula por la suma de dos vías paralelas: la indirecta suprime PCs vía interneuronas (desinhibe DN) y la directa activa PCs vía fibras paralelas (inhibe DN),
  - La supresión del simple spike domina antes del inicio del movimiento (iniciación) y la facilitación domina tras el inicio (terminación),

- p.5 🩺 Asthenia y adventitiousness reflejan fallos en las dos vías de salida

  - El reclutamiento diferencial de las dos vías es espacialmente congruente: PCs con campos receptivos en el brazo distal se suprimen mientras los DNCs con el mismo campo descargan en ráfaga,
  - Los signos clínicos de Holmes asthenia (fallo de reclutamiento, inicio lento) y adventitiousness (activación errática de músculos a suprimir) se atribuyen a malfunciones de los dos modos de salida (Ishikawa et al., 2015),

- p.5 📈 Evidencia electrofisiológica del cerebelo como predictor de estado

  - Los simple spikes de PCs reflejaron y precedieron la cinemática del movimiento independientemente de fuerzas asistivas/resistivas (Roitman; Pasalar; Ebner), pero un estudio en flexo-extensión de codo halló covariación con la fuerza, sugiriendo modelo inverso (Yamamoto et al., 2007),
  - Examinar la representación de las PCs no resuelve directamente la hipótesis, pues ambos modelos contienen representaciones cinemáticas y dinámicas y las PCs no son la salida final,

- p.6 🔗 La salida actual del cerebelo predice su entrada futura (correspondencia con filtro de Kalman)

  - Se analizaron 94 MFs, 83 PCs y 73 DNCs; una suma lineal ponderada de MFs reconstruyó las tasas de PCs y DNCs más parsimoniosamente que modelos de umbral, cuadrático o FIR, implicando una computación cerebelosa más lineal de lo supuesto,
  - Las tasas de las MFs en t+t1 se predijeron como suma lineal ponderada de los DNCs en t, significativamente frente a datos sustituto, confirmando que la salida actual contiene información predictiva de la entrada futura,
  - Las ecuaciones lineales derivadas se asemejan al filtro de Kalman: las PCs computan el estado predicho (predicción), los DNCs integran predicción y feedback (filtrado), y los DNCs predicen la entrada futura de las MFs (predicción cerebelosa),

- p.7 🤚 Evidencia conductual: la cinemática F1 es predictiva en controles y se retrasa en la ataxia

  - El ratio Br/Kr (coeficiente viscoso/elástico) evalúa la razón de control de velocidad frente a posición en movimientos de seguimiento de muñeca; la cinemática se descompone en un componente lento F1 (<0.5 Hz) y uno rápido F2 (>0.5 Hz),
  - En controles el componente F1 quedó solo ~60 ms (66.3 ± 29.4 ms) por detrás del objetivo, demasiado corto para ser feedback visual, indicando generación predictiva en el SNC,

- p.8 🏥 La predicción F1 está degradada en pacientes con ataxia cerebelosa

  - El retardo de F1 fue significativamente mayor en pacientes (172.1 ± 82.0 ms) que en controles (p < 0.0001), atribuible a pobre reclutamiento de facilitación en DN por menor desinhibición (asthenia),
  - El ratio Br/Kr del componente F1 fue menor en pacientes (0.99 ± 0.42) que en controles (1.73 ± 0.36; p < 0.001), mientras F2 fue comparable, indicando dificultad selectiva para reclutar control de velocidad predictivo,

- p.9 📉 El ratio Br/Kr de F1 es una medida clínica de la precisión del control predictivo

  - El ratio Br/Kr del componente F1 y el error F1 se correlacionaron negativamente,
  - El error F1 y la puntuación de seguimiento (tiempo del cursor dentro del objetivo) mostraron una correlación lineal negativa marcada, validando el Br/Kr de F1 como medida no invasiva de la precisión predictiva,

- p.9 🔬 El substrato morfológico del filtro de Kalman exige proyecciones de MF separadas

  - El requisito del filtro de Kalman es doble entrada: una MF desde el córtex cerebral (vía PN) para la predicción y otra MF que aporta feedback sensorial para el filtrado,
  - Kelly y Strick (2003) hallaron una fuerte proyección de M1 al cerebro-cerebelo (copia eferente) y Na et al. (2019) que las MFs de PN prácticamente no colateralizan a DN; las MFs de la LRN sí tienen abundante proyección colateral a DN (Wu et al., 1999),
  - En los datos propios, las poblaciones de MFs que reconstruyen PCs y DNCs fueron distintas (correlación media de pesos ≤0.060; p < 10⁻⁵), cumpliendo los requisitos del filtro de Kalman,

- p.9 🗜️ La predicción cerebelosa devuelve una representación comprimida al córtex

  - El pedúnculo cerebral lleva ~21 millones de axones corticales hacia PN, mientras el pedúnculo cerebeloso superior tiene solo ~0.8 millones, por lo que la salida del DN transmite menos del 5% de la información de la salida cortical,
  - La representación compacta podría ser beneficiosa o necesaria para extraer información relevante de entradas cerebelosas redundantes y asignar más atención a la tarea en foco,

- p.10 🧠 El cerebro-cerebelo se extiende a funciones cognitivas no motoras

  - Middleton y Strick (1994) demostraron, con transporte transneuronal de virus, que el cerebelo se conecta con el área prefrontal 46, revisando la visión de un cerebelo puramente motor,
  - Guell et al. (2018), con datos del Human Connectome Project (n=787), mapearon dos representaciones motoras (lóbulos I-VI y VIII) y tres regiones no motoras (Crus I, Crus II, lóbulos IX/X) ligadas a áreas de asociación, con dominios de memoria de trabajo, lenguaje, social y emocional,
  - Las lesiones del lóbulo posterior producen el síndrome cognitivo-afectivo cerebeloso (CCAS), con déficits de función ejecutiva, procesamiento visuoespacial, lenguaje y regulación del afecto,

- p.11 🧮 El modelo de Kalman es compatible con el cerebro-cerebelo no motor

  - La entrada principal MFa al cerebro-cerebelo puede originarse en áreas no motoras (prefrontal, parietal, temporal superior, occipitotemporal, parahipocampal) vía PN,
  - La entrada de filtrado MFb requeriría una fuente distinta con colaterales a DN, siendo candidatas la LRN y el núcleo reticular tegmental pontino (NRTP), que recibe entradas sensoriomotoras, prefrontales y parietales,

- p.11 🌐 Rol computacional especulado del bucle cerebro-cerebeloso: estabilizar dinámicas corticales

  - El córtex cerebral se modela como red neuronal recurrente (flexible pero propensa a inestabilidad caótica) y el cerebelo como red feedforward (estable, dependiente solo de entradas actuales),
  - Una red feedforward de más de dos capas puede aproximar cualquier mapeo continuo (base teórica de la transformada cerebelosa universal de Schmahmann),

- p.12 🤖 El cerebelo copia y estabiliza la dinámica del córtex como una red feedforward

  - Se propone que el cerebelo doma la dinámica caótica del córtex recurrente prediciendo su actividad esperada, análogo al algoritmo FORCE (Sussillo y Abbott, 2009),
  - Redes recurrentes y feedforward son computacionalmente equivalentes (backpropagation-through-time; descomposición de Schur), y la feedforward ofrece computación rápida de un solo paso,
  - Wagner et al. (2019) hallaron que las células piramidales de capa 5 del neocórtex y las granulares cerebelosas comparten características de codificación de tarea, apoyando la propagación de dinámicas neurales compartidas,

- p.12 ❓ Problemas futuros: aprendizaje motor y aproximación de dinámicas no lineales

  - El conjunto de datos provino de un mono sobreentrenado sin signos de aprendizaje, por lo que se demostró la actividad predictiva pero no el aspecto de aprendizaje motor del modelo directo,
  - Quedan dos preguntas abiertas: cómo utiliza el córtex cerebral la actividad predictiva cerebelosa, y cómo aproxima la dinámica lineal cerebelosa la dinámica no lineal del sistema musculoesquelético,
  - Nuevas técnicas como la imagen de calcio (Wagner et al., 2019) podrían rastrear cambios de actividad en múltiples neuronas durante el aprendizaje,

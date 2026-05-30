---
source_id: "doi:10.1016/s0959-4388(00)00153-7"
source_type: paper
title: Complementary roles of basal ganglia and cerebellum in learning and motor control
generated_at: 2026-05-30T19:16:34+00:00
---

- p.1 🧠 Los ganglios basales y el cerebelo no se limitan al control motor sino a funciones cognitivas

  - El daño a ambas estructuras produce déficits motores marcados, pero estudios de neuroimagen revelan su participación en tareas no motoras: imaginería mental, procesamiento sensorial, planificación, atención y lenguaje,
  - Ambas estructuras tienen conexiones recurrentes con la corteza cerebral a través del tálamo, formando múltiples canales 'paralelos' que proyectan no solo a cortezas motora y premotora, sino también prefrontal, temporal y parietal,
  - La actividad neural y los efectos de lesión de cada subsección se parecen a los del área cortical a la que proyecta, lo que dificulta distinguir sus roles solo por registro o lesión,
  - Pese a áreas diana solapadas, sus arquitecturas de circuito local y mecanismos sinápticos únicos sugieren que cada estructura se especializa en un tipo de procesamiento de información,

- p.1 🎓 El cerebelo, los ganglios basales y la corteza se especializan en tres tipos distintos de aprendizaje

  - El cerebelo se especializa en aprendizaje supervisado guiado por la señal de error codificada en las fibras trepadoras de la oliva inferior,
  - Los ganglios basales se especializan en aprendizaje por refuerzo guiado por la señal de recompensa codificada en las fibras dopaminérgicas de la sustancia negra,
  - La corteza cerebral se especializa en aprendizaje no supervisado basado en plasticidad hebbiana y conexiones recíprocas dentro y entre áreas corticales,

- p.1 💧 Las neuronas dopaminérgicas codifican predicción de recompensa futura, no recompensa presente

  - En una tarea de alcance condicionado, las neuronas dopaminérgicas responden inicialmente a la recompensa líquida, pero al aprender la tarea pasan a responder al estímulo visual condicionado y dejan de responder a la entrega de recompensa,
  - Esta respuesta predictiva coincide exactamente con la señal de diferencia temporal (TD) δ(t) = r(t) + V(t) – V(t–1), que actúa como error de predicción de recompensa y como señal de refuerzo del mapeo sensorio-motor,
  - En el modelo de RL, el estriosoma predice la recompensa futura del estado sensorial actual y la matriz predice recompensas asociadas a acciones candidatas, seleccionándose la acción de mayor recompensa esperada en SNr/GP,
  - El error TD se computa en SNc a partir de la entrada límbica (recompensa actual) y la entrada estriatal (recompensa futura); la posible base de V(t)–V(t–1) sería la disinhibición rápida por la matriz y la inhibición lenta por el estriosoma,

- p.3 🧩 La corteza, el estriado y las neuronas dopaminérgicas procesan la recompensa de forma distinta

  - La plasticidad cortico-estriatal está fuertemente modulada por dopamina, pero queda por aclarar si existen mecanismos plásticos diferentes en estriosoma y matriz,
  - Una comparación sistemática mostró que las neuronas corticales retienen más información sobre la entrada sensorial, las estriatales muestran mayor variedad de activación según el progreso de la tarea, y las dopaminérgicas responden sobre todo a recompensa o estímulos no predichos,
  - Esto sugiere que la corteza analiza la entrada sensorial, el estriado produce acciones y las neuronas dopaminérgicas son responsables del aprendizaje de nuevas conductas,

- p.3 👁️ La LTD de las células de Purkinje dependiente de fibra trepadora es el sustrato del aprendizaje por error

  - La idea del cerebelo como sistema supervisado se remonta a Marr y Albus, e Ito mostró en la adaptación del reflejo vestíbulo-ocular que la LTD de las sinapsis de Purkinje dependiente de fibra trepadora es el sustrato del aprendizaje por error,
  - Durante respuestas de seguimiento ocular, el ajuste de las espigas complejas es la imagen especular del de las espigas simples, coherente con que la LTD moldea las espigas simples mediante la señal de error de las fibras trepadoras,
  - Kitazawa et al. mostraron que las espigas complejas codifican la dirección del objetivo al inicio del movimiento de alcance y el error de punto final cerca del final, siendo esta última codificación consistente con la hipótesis de LTD,

- p.3 🔗 Conductas específicas surgen de combinar módulos de aprendizaje distribuidos en las tres áreas

  - Cada estructura no se especializa en qué hacer sino en cómo aprenderlo, realizándose funciones concretas por combinación de múltiples módulos de aprendizaje,
  - Los modelos internos del cuerpo y el entorno, que mejoran el control motor, podrían adquirirse por aprendizaje supervisado con el comando motor como entrada y el resultado sensorial como señal de enseñanza,
  - El aprendizaje no supervisado puede ayudar a extraer la información esencial de la entrada sensorial cruda al servicio del aprendizaje supervisado o por refuerzo,

- p.4 👀 La adaptación de sacádicos y la modulación por recompensa del caudado ilustran ambos aprendizajes

  - La adaptación de ganancia separada según el tipo de sacádico (guiado visualmente vs guiado por memoria) es lo esperado de un modelo supervisado cerebeloso, donde solo se modifican los pesos asociados a la señal de error retiniano,
  - En experimentos de sacádico retardado con recompensa en una sola de cuatro direcciones, la sintonía direccional de las neuronas caudadas fue fuertemente modulada por la condición de recompensa,
  - Esto sugiere que las neuronas estriatales no representan la acción motora en sí sino la recompensa asociada al estado y las acciones, especulándose que las neuronas que siguen la recompensa están en el estriosoma y las moduladas por recompensa en la matriz,

- p.4 💪 El cerebelo media movimientos guiados externamente y los ganglios basales los generados internamente

  - Estudios de alcance en monos muestran que el cerebelo participa en movimiento guiado visualmente y los ganglios basales en movimiento generado internamente (guiado por memoria),
  - En el tálamo motor, las neuronas que reciben input cerebeloso y proyectan a corteza premotora ventral se activan selectivamente en movimientos guiados visualmente, mientras que las que reciben input de ganglios basales y proyectan a prefrontal son selectivas para movimientos generados internamente,
  - En movimientos guiados visualmente lo crítico es la transformación de coordenadas visuales a motoras (aprendizaje supervisado cerebeloso); en los generados internamente lo crítico es la selección de acción y supresión, que requieren predicción del valor de recompensa,

- p.5 🔁 Dos bucles cortico-ganglios basales con representaciones distintas aprenden secuencias

  - Las áreas del bucle prefrontal (corteza prefrontal, preSMA, cabeza del caudado) intervienen en el aprendizaje de secuencias nuevas, mientras que las del bucle motor (SMA, cuerpo del putamen) intervienen en la ejecución de movimientos bien aprendidos,
  - La hipótesis es que ambos bucles aprenden la secuencia con representaciones distintas: coordenadas visuoespaciales en el bucle prefrontal y coordenadas motoras en el bucle motor,
  - Un modelo de RL basado en esta hipótesis replicó el curso temporal del aprendizaje, el rendimiento ante secuencias modificadas y los resultados de lesiones; experimentos psicofísicos confirmaron que los humanos dependen cada vez más de la representación corporal con el progreso del aprendizaje,

- p.5 ⏱️ El cerebelo anterior y posterior usan representaciones distintas para tiempo y ritmo

  - La memoria de ritmos simples implica el cerebelo anterior, mientras que la de ritmos complejos y el ajuste de la temporización ante disparadores externos irregulares implican el cerebelo posterior,
  - El cerebelo anterior aportaría modelos internos de la dinámica corporal útiles para predecir temporización regular y controlar parámetros detallados del movimiento,
  - El cerebelo posterior aportaría modelos internos para predicción de eventos sensoriales, útiles en la percepción y el ajuste de la temporización,

- p.5 🧮 Los bucles cortico-ganglios basales participan en planificación cognitiva multietapa

  - Hay datos abundantes de neuroimagen de participación de ambas estructuras en imaginería mental, discriminación sensorial, planificación, atención y lenguaje, y estudios de pacientes muestran deterioros que se extienden a funciones cognitivas,
  - Estudios de lesión en roedores sugieren participación de los ganglios basales en aprendizaje basado en reglas y navegación espacial,
  - En un estudio PET con la tarea Torre de Londres, la actividad del núcleo caudado y de cortezas premotora y prefrontal correlacionó con la complejidad de la tarea, sugiriendo participación en la planificación de acciones en múltiples pasos,

- p.5 🏔️ El uso de algoritmos y de representaciones distintos explica la involucración diferencial de cada estructura

  - El uso de distintos algoritmos de aprendizaje se asocia a la participación diferencial de cerebelo, ganglios basales y corteza; el uso de distintas representaciones se asocia a la participación diferencial de los canales dentro de los bucles cortico-ganglios basales y cortico-cerebelosos,
  - La actividad de las neuronas corticales podría ser solo la punta del iceberg, resultado de la dinámica recurrente de los bucles cortico-ganglios basales y cortico-cerebelosos,
  - Un papel importante de la corteza cerebral es proporcionar representaciones comunes sobre las que los ganglios basales y el cerebelo puedan trabajar conjuntamente,

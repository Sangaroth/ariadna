---
source_id: "doi:10.3389/fnhum.2014.00443"
source_type: paper
title: How to measure metacognition
generated_at: 2026-05-30T16:06:25+00:00
---

- p.1 🧠 La metacognición se mide como la correspondencia entre exactitud y confianza, distinguiendo sensibilidad de sesgo

  - El grado de asociación entre exactitud y confianza ensayo a ensayo se toma como medida cuantitativa de metacognición,
  - Coeficientes de correlación como la r de Pearson son susceptibles a influencias indeseadas como los sesgos de respuesta,
  - La sensibilidad metacognitiva (distinguir juicios propios correctos de incorrectos) y el sesgo metacognitivo (over-/underconfidence) son constructos disociables aunque a menudo se confunden,
  - La sensibilidad suele estar afectada por el propio rendimiento de la tarea, mientras la eficiencia metacognitiva sería independiente del nivel de rendimiento,

- p.2 📊 La tabla 2×2 confianza-exactitud es el punto de partida y define la SDT de "tipo 2"

  - La tabla cuenta confianza alta/baja asignada a juicios correctos e incorrectos (H2, M2, FA2, CR2),
  - En la SDT de tipo 1 la distribución relevante es P(respuesta, estímulo); en tipo 2 las confianzas se condicionan a las respuestas del observador, no al estado objetivo del mundo,
  - El análisis asume que la fuerza del estímulo se mantiene constante ("método de estímulos constantes"), atribuyendo fluctuaciones a ruido interno,
  - La correlación phi (φ) es la r de Pearson entre exactitud y confianza codificadas como vectores binarios,

- p.2 ⚠️ Las correlaciones phi y gamma están contaminadas por el sesgo metacognitivo

  - El coeficiente gamma de Goodman-Kruskal, popular en memoria, fue defendido por Nelson (1984) por no asumir distribuciones de la SDT,
  - Phi es "margin sensitive": su valor depende de los conteos marginales de la tabla que reflejan rendimiento y sesgo,
  - Masson y Rotello (2009) mostraron por simulación que G es sensible a la tendencia a usar confianzas altas o bajas, llevando a conclusiones erróneas,

- p.3 📐 El d′ de tipo 2 intenta eliminar el sesgo pero falla por sus supuestos gaussianos

  - Type 2 d′ = z(H2) − z(FA2), análogo al d′ de tipo 1, y teóricamente independiente del sesgo,
  - El supuesto de distribuciones gaussianas de igual varianza, aceptable en tipo 1, es muy problemático en tipo 2,
  - Galvin et al. (2003) mostraron que esas distribuciones son de varianza distinta y no gaussianas si se cumple la igualdad de varianza en tipo 1,
  - Evans y Azzopardi (2007) mostraron que el d′ de tipo 2 de Kunimoto et al. (2001) queda confundido por cambios en el sesgo,

- p.3 📈 El análisis ROC de tipo 2 ofrece una medida no paramétrica y libre de sesgo (AUROC2)

  - El AUROC se construye con múltiples criterios de respuesta, donde 0.5 indica rendimiento al azar y áreas mayores mayor sensibilidad,
  - Con múltiples niveles de confianza cada nivel actúa como un criterio que separa confianza alta de baja, generando la curva ROC de tipo 2 completa,
  - El AUROC2 es libre de sesgo y, a diferencia del d′ de tipo 2, no hace supuestos paramétricos falsos,
  - Sin embargo, Galvin et al. (2003) mostraron que AUROC2 está afectado por el d′ de tipo 1 y la colocación del criterio de tipo 1,

- p.3 🎯 El meta-d′ aprovecha que el rendimiento de tipo 1 restringe el rendimiento máximo de tipo 2

  - Conocidas las varianzas gaussianas de tipo 1, las formas de las distribuciones de tipo 2 quedan determinadas aunque no sean gaussianas,
  - Si la sensibilidad de tipo 1 es cero, la sensibilidad metacognitiva de tipo 2 también debe serlo, pues los aciertos son por azar,

- p.4 🏆 El meta-d′ define la eficiencia metacognitiva como meta-d′/d′ y es la mejor medida disponible

  - El meta-d′ es la sensibilidad de tipo 1 del observador ideal, expresada en unidades de d′ (relación señal-ruido disponible para la metacognición),
  - Para un observador metacognitivamente ideal meta-d′ = d′; si meta-d′ < d′ la sensibilidad es subóptima dentro del marco SDT,
  - Un meta-d′/d′ de 0.7 indica 70% de eficiencia (se pierde 30% de la evidencia sensorial); también se usa la diferencia meta-d′ − d′ o el log del cociente,
  - Barrett et al. (2013) hallaron que meta-d′ es robusto a cambios de sesgo y recupera cambios simulados en sensibilidad,

- p.4 🔗 El modelo SDRM modela las causas de la inexactitud metacognitiva mediante dos muestreos de evidencia

  - El SDRM de Jang et al. (2012) asume dos muestreos de "evidencia" por estímulo, uno para la conducta de primer orden y otro para la confianza,
  - Las muestras se extraen de una distribución bivariada con parámetro de correlación ρ que explica las disociaciones entre confianza y exactitud,
  - A diferencia del meta-d′, el SDRM separa el ruido en la colocación de criterios de confianza del ruido en la evidencia,
  - El SDRM requiere considerable interpretación de los ajustes de parámetros, mientras meta-d′ es más simple de calcular,

- p.5 🎚️ El sesgo metacognitivo es la tendencia global a dar confianza alta, manifestada según cómo se elicite

  - La medida más simple es el porcentaje de ensayos de confianza alta o la confianza media a lo largo de los ensayos,
  - En la SDT un sesgo más liberal aprieta los criterios de confianza hacia el criterio de decisión central,
  - Con una escala 1–6 (de seguro "A" a seguro "B"), un sesgo más liberal aumenta el uso de los extremos y reduce el uso del centro de la escala,

- p.5 🪟 Las funciones psicométricas y las medidas de discrepancia "one-shot" tienen limitaciones para aislar la metacognición

  - La sensibilidad puede medirse como la diferencia de pendiente entre funciones psicométricas de confianza alta y baja, aunque este método puede no ser libre de sesgo,
  - Las medidas de discrepancia "one-shot" (autovaloración global comparada con rendimiento) se usan en literatura clínica y psicología social,
  - Con una sola valoración no es posible separar sesgo de sensibilidad ni medir eficiencia; se requieren medidas ensayo a ensayo,

- p.5 🌦️ La confianza metacognitiva se formaliza como un juicio de probabilidad sobre la propia actuación

  - Un pronosticador está bien calibrado si su predicción media (p. ej. 60%) coincide con la frecuencia real a largo plazo,
  - Hay casos discretos (probabilidades a afirmaciones particulares) y continuos (intervalos de confianza); el foco está en los discretos,
  - Una ventaja del marco probabilístico es que una valoración de 0.7 puede contrastarse con la probabilidad objetiva de ser correcto, a diferencia de una confianza de "4",

- p.6 🧮 El Brier score y su descomposición en calibración y resolución reflejan el mismo confound de rendimiento que la SDT

  - El "probability score" es la diferencia al cuadrado entre la valoración f y su ocurrencia c; su media es el Brier score, análogo al coeficiente phi,
  - Murphy (1973) descompone el Brier score en PS = O + C − R: índice de resultado (O), calibración (C) y resolución (R),
  - O es máximo cuando el rendimiento está cerca del azar, confirmando que correlaciones simples están influidas por el rendimiento de la tarea,
  - Un hallazgo típico es que los observadores son overconfident: sus juicios de probabilidad superan el % medio de aciertos,

- p.6 🧩 Distinguir sensibilidad de eficiencia abre aplicaciones para una psicología de la metacognición

  - Muchos hallazgos "clásicos" (p. ej. mejor sensibilidad de los JOLs con demora, Nelson y Dunlosky, 1991) se basan en G, posiblemente confundido por sesgo y rendimiento,
  - La eficiencia metacognitiva permite comparar dominios donde no se puede igualar el rendimiento, como tareas visuales y de memoria con correlatos neurales distintos,
  - Weil et al. (2013) mostraron que la eficiencia metacognitiva aumenta en la adolescencia, consistente con la maduración prefrontal,

- p.7 🧠 El efecto Dunning-Kruger admite interpretaciones distintas en términos de sensibilidad y eficiencia

  - Kruger y Dunning (1999) hallaron que los peores ejecutores mostraban mayor discrepancia entre rendimiento real y autovaloración one-shot,
  - Una interpretación es consecuencia directa de que la sensibilidad metacognitiva está determinada por el d′ de tipo 1 (valoraciones más ruidosas),
  - La otra (preferida por los autores) es que la habilidad y la eficiencia metacognitiva comparten recursos, generando una relación no lineal,

- p.7 👁️ Equiparar sensibilidad metacognitiva con conciencia es problemático

  - Lau (2008) argumenta que el d′ de tipo 1 no debe tomarse como medida de conciencia porque el procesamiento inconsciente también puede impulsarlo (p. ej. blindsight),
  - Lau y Passingham (2006) crearon condiciones igualadas en d′ de tipo 1 pero distintas en conciencia subjetiva, reflejando una diferencia de sesgo metacognitivo,
  - Kolb y Braun (1995) crearon estímulos con d′ de tipo 1 positivo pero sensibilidad metacognitiva casi nula, aunque el hallazgo fue difícil de replicar,

- p.7 🌗 Una baja sensibilidad metacognitiva no implica inequívocamente ausencia de experiencia consciente

  - La sensibilidad metacognitiva se calcula respecto al mundo externo, no respecto a la experiencia del sujeto, desconocida para el experimentador,
  - Una baja sensibilidad podría deberse a alucinaciones: el sujeto ve vívidamente un blanco falso y expresa alta confianza (una falsa alarma de tipo 2),
  - Aun así, los autores reconocen la estrecha relación entre sensibilidad metacognitiva y conciencia en experimentos de laboratorio sin psicosis,

- p.8 ✅ Se recomienda usar medidas libres de sesgo y tratar el sesgo metacognitivo, no la sensibilidad, como índice de conciencia

  - La sensibilidad metacognitiva mide la capacidad de introspección, no cuánta experiencia consciente se introspecciona en cada ensayo,
  - En el "blindsight de tipo 2" los pacientes desarrollan una "corazonada" que impulsa sensibilidad por encima del azar sin experiencia visual consciente reconocida,
  - Los autores instan a aplicar las medidas libres de sesgo (SDT/ROC) en estudios futuros y advierten contra equiparar directamente sensibilidad con conciencia,
  - Proponen tomar el sesgo metacognitivo como reflejo de los niveles de conciencia y la sensibilidad como trasfondo de referencia,

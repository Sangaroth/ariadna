---
page_id: how-to-measure-metacognition
page_type: entity_work
canonical_name: How to measure metacognition
domain_primary: social-sciences.psychology.cognitive-psychology
aliases: 
- Fleming & Lau 2014
- How to measure metacognition (Fleming & Lau)
- Fleming SM, Lau HC 2014
relations:
- type: developed_by
  to: stephen-fleming
  weight: canonical
- type: developed_by
  to: hakwan-lau
  weight: canonical
- type: discusses
  to: meta-d-prime
  weight: strong
- type: discusses
  to: eficiencia-metacognitiva
  weight: strong
- type: discusses
  to: sensibilidad-metacognitiva
  weight: strong
- type: discusses
  to: sesgo-metacognitivo
  weight: strong
- type: discusses
  to: auroc2
  weight: strong
- type: discusses
  to: teoria-deteccion-senales-tipo-2
  weight: strong
- type: discusses
  to: medidas-correlacionales-phi-gamma
  weight: related
- type: discusses
  to: modelo-sdrm
  weight: related
- type: discusses
  to: brier-score-calibracion-resolucion
  weight: related
- type: discusses
  to: metacognicion-como-indice-de-conciencia
  weight: strong
- type: discusses
  to: efecto-dunning-kruger
  weight: related
- type: introduces
  to: d-prime-tipo-2
  weight: related
- type: introduces
  to: blindsight-tipo-2
  weight: related
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# How to measure metacognition

## Descripción

*How to measure metacognition* es un artículo de revisión publicado por [[stephen-fleming]] y [[hakwan-lau]] en *Frontiers in Human Neuroscience* (2014). Su tesis vertebradora es metodológica y conceptual: la metacognición se cuantifica como la correspondencia entre exactitud y confianza ensayo a ensayo, pero esa correspondencia esconde dos constructos disociables que la literatura confunde sistemáticamente —la **sensibilidad metacognitiva** (capacidad de discriminar los propios juicios correctos de los incorrectos) y el **sesgo metacognitivo** (tendencia global a la sobre- o infraconfianza)— y que, además, la sensibilidad se contamina con el nivel de rendimiento de la tarea de primer orden [How to measure metacognition, p.1](https://doi.org/10.3389/fnhum.2014.00443#page=1).

## Contenido y argumento

El trabajo recorre las medidas disponibles en orden de creciente adecuación, tomando como punto de partida la tabla 2×2 confianza-exactitud (H2, M2, FA2, CR2) que da pie a la [[teoria-deteccion-senales-tipo-2]]: a diferencia de la teoría de detección de señales de tipo 1 —donde la distribución relevante es P(respuesta, estímulo)—, en tipo 2 las confianzas se condicionan a las respuestas del observador y no al estado objetivo del mundo [How to measure metacognition, p.2](https://doi.org/10.3389/fnhum.2014.00443#page=2).

A partir de ahí, los autores critican las [[medidas-correlacionales-phi-gamma]]: la correlación phi es *margin sensitive* (depende de los conteos marginales que reflejan rendimiento y sesgo) y el gamma de Goodman-Kruskal, defendido por Nelson (1984) en la literatura de memoria, resulta —según Masson y Rotello (2009)— sensible a la tendencia a usar confianzas altas o bajas [How to measure metacognition, p.2](https://doi.org/10.3389/fnhum.2014.00443#page=2). El [[d-prime-tipo-2]] intenta corregir el sesgo pero falla por supuestos gaussianos de igual varianza que Galvin et al. (2003) demostraron insostenibles [How to measure metacognition, p.3](https://doi.org/10.3389/fnhum.2014.00443#page=3). El análisis [[auroc2]] aporta una medida no paramétrica y libre de sesgo, aunque sigue afectada por el d′ de tipo 1 [How to measure metacognition, p.3](https://doi.org/10.3389/fnhum.2014.00443#page=3).

La propuesta central es el [[meta-d-prime]], que aprovecha que el rendimiento de tipo 1 restringe el máximo posible de tipo 2 y permite expresar la sensibilidad metacognitiva en las mismas unidades que el d′; su cociente meta-d′/d′ define la [[eficiencia-metacognitiva]], independiente del nivel de rendimiento y robusta a cambios de sesgo según Barrett et al. (2013) [How to measure metacognition, p.4](https://doi.org/10.3389/fnhum.2014.00443#page=4). Como alternativa generativa se reseña el [[modelo-sdrm]] de Jang et al. (2012), que modela las causas de la inexactitud mediante dos muestreos correlacionados de evidencia [How to measure metacognition, p.4](https://doi.org/10.3389/fnhum.2014.00443#page=4).

En paralelo, el artículo formaliza la confianza como juicio probabilístico (un pronosticador bien calibrado, casos discretos y continuos) y revisa el [[brier-score-calibracion-resolucion]], cuya descomposición de Murphy (1973) PS = O + C − R reproduce el mismo confound de rendimiento que la SDT [How to measure metacognition, p.6](https://doi.org/10.3389/fnhum.2014.00443#page=6).

## Aplicaciones e implicaciones

La distinción sensibilidad/eficiencia reinterpreta hallazgos clásicos: el [[efecto-dunning-kruger]] como posible consecuencia directa del d′ de tipo 1, y la maduración prefrontal en la adolescencia (Weil et al., 2013) como aumento de eficiencia metacognitiva [How to measure metacognition, p.6](https://doi.org/10.3389/fnhum.2014.00443#page=6). El cierre se dedica a la [[metacognicion-como-indice-de-conciencia]]: los autores advierten contra equiparar sensibilidad metacognitiva con conciencia —ejemplos como el [[blindsight-tipo-2]] muestran sensibilidad por encima del azar sin experiencia visual consciente— y proponen tratar el sesgo metacognitivo, no la sensibilidad, como reflejo de los niveles de conciencia [How to measure metacognition, p.8](https://doi.org/10.3389/fnhum.2014.00443#page=8).

## Relevancia para el atlas

Dentro del paradigma teleosemántico, el paper es la referencia metodológica del pilar de **metacognición y metarrepresentación**: ofrece el instrumental para medir la introspección como función biológica medible, y conecta esa medida con el problema de la conciencia y con comparaciones transdominio (memoria vs. percepción) imposibles de igualar en rendimiento bruto.

## Citations

- [How to measure metacognition, p.1](https://doi.org/10.3389/fnhum.2014.00443#page=1)
- [How to measure metacognition, p.2](https://doi.org/10.3389/fnhum.2014.00443#page=2)
- [How to measure metacognition, p.3](https://doi.org/10.3389/fnhum.2014.00443#page=3)
- [How to measure metacognition, p.4](https://doi.org/10.3389/fnhum.2014.00443#page=4)
- [How to measure metacognition, p.5](https://doi.org/10.3389/fnhum.2014.00443#page=5)
- [How to measure metacognition, p.6](https://doi.org/10.3389/fnhum.2014.00443#page=6)
- [How to measure metacognition, p.7](https://doi.org/10.3389/fnhum.2014.00443#page=7)
- [How to measure metacognition, p.8](https://doi.org/10.3389/fnhum.2014.00443#page=8)

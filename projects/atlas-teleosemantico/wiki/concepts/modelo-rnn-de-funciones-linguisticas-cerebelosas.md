---
page_id: modelo-rnn-de-funciones-linguisticas-cerebelosas
page_type: concept
canonical_name: Modelo de red neuronal recurrente de las funciones lingüísticas cerebelosas
domain_primary: life-sciences.neuroscience.computational-neuroscience
primary_domains:
- life-sciences.neuroscience.computational-neuroscience
- social-sciences.linguistics.psycholinguistics
- life-sciences.neuroscience.cognitive-neuroscience
aliases: 
- Cerebellar language RNN model
- RNN de predicción de la palabra siguiente
- Modelo recurrente del lenguaje cerebeloso
relations:
- type: related_to
  to: modelo-interno-directo
  weight: strong
- type: related_to
  to: memoria-de-trabajo-verbal-cerebelosa
  weight: strong
- type: related_to
  to: merge-operacion-sintactica
  weight: weak
- type: related_to
  to: evolucion-cerebro-cerebelosa-del-lenguaje
  weight: strong
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Modelo de red neuronal recurrente de las funciones lingüísticas cerebelosas

## Definición

Es un modelo computacional que aborda el papel del cerebelo en el lenguaje distinguiendo dos funciones: una **función lingüística motora**, asociada al lóbulo VI medial bilateral y al núcleo dentado rostral/dorsal, que controla la articulación, y una **función cognitiva no motora**, residente en el cerebelo lateral derecho (lóbulo VI, Crus I/II) [Consensus Paper: Models of Cerebellar Functions, p.22](https://doi.org/10.1007/s12311-025-01939-3#page=22).

## Arquitectura

Para modelar la función cognitiva se construyó una **red neuronal recurrente (RNN) de tres capas** con vías feedforward y feedback que modela la predicción de la palabra siguiente, asumiendo que la oliva inferior calcula el error de predicción [Consensus Paper: Models of Cerebellar Functions, p.22](https://doi.org/10.1007/s12311-025-01939-3#page=22). El resultado más notable es que la **capa intermedia**, correspondiente a las células de Purkinje, desarrolló de forma espontánea capacidad de procesamiento sintáctico, unificando la predicción de palabras y el procesamiento sintáctico como dos salidas de una sola computación [Consensus Paper: Models of Cerebellar Functions, p.22](https://doi.org/10.1007/s12311-025-01939-3#page=22).

## Relevancia teleosemántica

El modelo extiende el principio del [[modelo-interno-directo]] cerebeloso —predicción guiada por error— al dominio lingüístico, conectando con la [[memoria-de-trabajo-verbal-cerebelosa]] y con la [[evolucion-cerebro-cerebelosa-del-lenguaje]]. Para el atlas es relevante como evidencia de cognición jerárquica transdominio: la sintaxis emerge como subproducto de una predicción secuencial, ilustrando cómo una función predictiva general puede dar lugar a contenido lingüístico estructurado sin un mecanismo dedicado.

## Citations

- [Consensus Paper: Models of Cerebellar Functions, p.22](https://doi.org/10.1007/s12311-025-01939-3#page=22)

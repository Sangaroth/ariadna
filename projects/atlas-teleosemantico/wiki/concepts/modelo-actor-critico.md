---
page_id: modelo-actor-critico
page_type: concept
canonical_name: Modelo actor/crítico de selección de acción
domain_primary: computer_science.artificial_intelligence.reinforcement_learning
primary_domains:
- computer_science.artificial_intelligence.reinforcement_learning
- life_sciences.neuroscience.computational_neuroscience
- social_sciences.psychology.learning
aliases: 
- actor/critic
- arquitectura actor-crítico
- actor-critic
relations:
- type: part_of
  to: aprendizaje-por-refuerzo-ganglios-basales
  weight: canonical
- type: related_to
  to: control-model-based-vs-model-free
  weight: canonical
- type: related_to
  to: error-de-diferencia-temporal-dopaminergico
  weight: canonical
- type: developed_by
  to: nathaniel-daw
  weight: related
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Modelo actor/crítico de selección de acción

## Definición

Marco computacional del [[aprendizaje-por-refuerzo-ganglios-basales|aprendizaje por refuerzo]] en el que un **crítico** aprende a predecir la recompensa futura asociada a estados y un **actor** elige acciones según una política aprendida; el [[error-de-diferencia-temporal-dopaminergico|error de predicción]] actualiza tanto las predicciones de valor del crítico como las probabilidades de acción del actor [Human and Rodent Homologies in Action Control: Corticostriatal Determinants of Goal-Directed and Habitual Action, p.13](https://doi.org/10.1038/npp.2009.131#page=13).

## Mapeo neural

O'Doherty et al (2004) hallaron señales de error de predicción en el estriado dorsal solo durante tareas instrumentales —consistente con el papel de **actor**— y en el estriado ventral durante tareas tanto instrumentales como pavlovianas —consistente con el papel de **crítico** [Human and Rodent Homologies in Action Control, p.14](https://doi.org/10.1038/npp.2009.131#page=14).

## Relación con el control dirigido a metas

Daw et al (2005) propusieron que el actor/crítico aprende valores S-R habituales (cacheados, *model-free*) mientras un modelo prospectivo (*model-based*) computa valores en línea sensibles a la [[devaluacion-del-resultado|devaluación]]; el control del comportamiento dependería de una competición basada en incertidumbre entre ambos sistemas [Human and Rodent Homologies in Action Control, p.14](https://doi.org/10.1038/npp.2009.131#page=14). Esta dualidad es la base computacional del [[control-model-based-vs-model-free|contraste model-based vs model-free]].

## Citations

- [Human and Rodent Homologies in Action Control: Corticostriatal Determinants of Goal-Directed and Habitual Action, p.13](https://doi.org/10.1038/npp.2009.131#page=13)
- [Human and Rodent Homologies in Action Control: Corticostriatal Determinants of Goal-Directed and Habitual Action, p.14](https://doi.org/10.1038/npp.2009.131#page=14)

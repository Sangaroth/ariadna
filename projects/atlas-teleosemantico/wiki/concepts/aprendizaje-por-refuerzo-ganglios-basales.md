---
page_id: aprendizaje-por-refuerzo-ganglios-basales
page_type: concept
canonical_name: Aprendizaje por refuerzo en los ganglios basales
domain_primary: natural-sciences.neuroscience.behavioral-neuroscience
primary_domains:
- natural-sciences.neuroscience.behavioral-neuroscience
- natural-sciences.computer-science.artificial-intelligence
- social-sciences.psychology.cognitive-psychology
aliases: 
- basal ganglia reinforcement learning
- aprendizaje por refuerzo
- dopamine reward signal
- RL en estriado
relations:
- type: related_to
  to: tres-algoritmos-de-aprendizaje-cerebro
  weight: canonical
- type: related_to
  to: error-de-diferencia-temporal-dopaminergico
  weight: canonical
- type: related_to
  to: estriosoma-y-matriz
  weight: strong
- type: related_to
  to: nucleo-caudado-y-aprendizaje-de-habitos
  weight: strong
- type: contrasts_with
  to: aprendizaje-supervisado-cerebeloso
  weight: strong
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Aprendizaje por refuerzo en los ganglios basales

## Definición

El **aprendizaje por refuerzo en los ganglios basales** es la clase de aprendizaje en la que el estriado y sus estructuras asociadas ajustan la selección de acciones guiados por una señal de recompensa, codificada en las fibras dopaminérgicas procedentes de la sustancia negra [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.1](https://doi.org/10.1016/s0959-4388(00)00153-7#page=1). Es el caso paradigmático del aprendizaje de hábitos y disposiciones de respuesta del [[nucleo-caudado-y-aprendizaje-de-habitos|estriado]].

## Arquitectura computacional

En el modelo de aprendizaje por refuerzo, el [[estriosoma-y-matriz|estriosoma]] predice la recompensa futura del estado sensorial actual y la matriz predice las recompensas asociadas a las acciones candidatas, seleccionándose en SNr/GP la acción de mayor recompensa esperada [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.1](https://doi.org/10.1016/s0959-4388(00)00153-7#page=1). El [[error-de-diferencia-temporal-dopaminergico|error de diferencia temporal (TD)]] se computa en la SNc a partir de la entrada límbica (recompensa actual) y la entrada estriatal (recompensa futura), y actúa como señal de refuerzo del mapeo sensorio-motor [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.1](https://doi.org/10.1016/s0959-4388(00)00153-7#page=1).

## Evidencia: la recompensa, no la acción

Una comparación sistemática mostró que las neuronas estriatales presentan mayor variedad de activación según el progreso de la tarea, mientras que las dopaminérgicas responden sobre todo a recompensa o estímulos no predichos, sugiriendo que el estriado produce acciones y las neuronas dopaminérgicas son responsables del aprendizaje de nuevas conductas [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.3](https://doi.org/10.1016/s0959-4388(00)00153-7#page=3). En experimentos de sacádico retardado con recompensa en una sola de cuatro direcciones, la sintonía direccional de las neuronas caudadas estuvo fuertemente modulada por la condición de recompensa, lo que sugiere que las neuronas estriatales no representan la acción motora en sí sino la recompensa asociada al estado y a las acciones [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.4](https://doi.org/10.1016/s0959-4388(00)00153-7#page=4). Esta firma de valor es lo que se vuelve crítico en los movimientos generados internamente, donde lo decisivo es la selección de acción y la supresión, que requieren predecir el valor de recompensa [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.4](https://doi.org/10.1016/s0959-4388(00)00153-7#page=4).

## Citations

- [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.1](https://doi.org/10.1016/s0959-4388(00)00153-7#page=1)
- [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.3](https://doi.org/10.1016/s0959-4388(00)00153-7#page=3)
- [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.4](https://doi.org/10.1016/s0959-4388(00)00153-7#page=4)

---
page_id: error-de-diferencia-temporal-dopaminergico
page_type: concept
canonical_name: Error de diferencia temporal y predicción de recompensa dopaminérgica
domain_primary: natural-sciences.neuroscience.behavioral-neuroscience
primary_domains:
- natural-sciences.neuroscience.behavioral-neuroscience
- natural-sciences.computer-science.artificial-intelligence
aliases: 
- temporal difference error
- TD error
- error de predicción de recompensa
- dopamine reward prediction
relations:
- type: related_to
  to: aprendizaje-por-refuerzo-ganglios-basales
  weight: canonical
- type: related_to
  to: estriosoma-y-matriz
  weight: strong
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Error de diferencia temporal y predicción de recompensa dopaminérgica

## Definición

El **error de diferencia temporal (TD)** es la señal que computa la diferencia entre la recompensa predicha y la obtenida y que, en el cerebro, encarnan las neuronas dopaminérgicas. El hallazgo clave es que estas neuronas codifican la *predicción* de recompensa futura, no la recompensa presente [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.1](https://doi.org/10.1016/s0959-4388(00)00153-7#page=1).

## El desplazamiento de la respuesta

En una tarea de alcance condicionado, las neuronas dopaminérgicas responden inicialmente a la recompensa líquida, pero al aprender la tarea pasan a responder al estímulo visual condicionado y dejan de responder a la entrega de recompensa [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.1](https://doi.org/10.1016/s0959-4388(00)00153-7#page=1). Esta respuesta predictiva coincide exactamente con la señal TD δ(t) = r(t) + V(t) − V(t−1), que actúa simultáneamente como error de predicción de recompensa y como señal de refuerzo del mapeo sensorio-motor [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.1](https://doi.org/10.1016/s0959-4388(00)00153-7#page=1).

## Sustrato del cómputo

El error TD se computa en la SNc a partir de la entrada límbica (recompensa actual) y la entrada estriatal (recompensa futura); la base candidata del término V(t) − V(t−1) sería la combinación de la disinhibición rápida aportada por la matriz y la inhibición lenta aportada por el [[estriosoma-y-matriz|estriosoma]] [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.1](https://doi.org/10.1016/s0959-4388(00)00153-7#page=1). La plasticidad cortico-estriatal está fuertemente modulada por dopamina, aunque queda por aclarar si existen mecanismos plásticos diferentes en estriosoma y matriz [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.3](https://doi.org/10.1016/s0959-4388(00)00153-7#page=3).

## Citations

- [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.1](https://doi.org/10.1016/s0959-4388(00)00153-7#page=1)
- [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.3](https://doi.org/10.1016/s0959-4388(00)00153-7#page=3)

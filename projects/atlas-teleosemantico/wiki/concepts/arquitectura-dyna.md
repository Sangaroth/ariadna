---
page_id: arquitectura-dyna
page_type: concept
canonical_name: Arquitectura Dyna
domain_primary: life_sciences.neuroscience.computational_neuroscience
primary_domains:
- life_sciences.neuroscience.computational_neuroscience
- social_sciences.psychology.cognitive_psychology
aliases: 
- Dyna architecture
- Aprendizaje por refuerzo basado en modelo con planificación off-line
relations:
- type: related_to
  to: control-model-based-vs-model-free
  weight: canonical
- type: related_to
  to: cerebelo-como-simulador-off-line
  weight: canonical
- type: related_to
  to: replay-hipocampal
  weight: supporting
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Arquitectura Dyna

## Definición

Arquitectura de aprendizaje por refuerzo, citada entre las inspiraciones computacionales del marco de Bhattacharya et al., que integra aprendizaje a partir de experiencia real con *planificación off-line* sobre experiencia simulada por un modelo interno del entorno [Role of cerebellum in sleep-dependent memory processes, p.8](https://doi.org/10.3389/fnsys.2023.1154489#page=8). En Dyna, un mismo algoritmo de actualización de valores se aplica tanto a transiciones reales como a transiciones generadas internamente por el modelo, lo que permite refinar la política sin nueva interacción con el mundo.

Su pertinencia para el atlas radica en que ofrece una plantilla formal del [[cerebelo-como-simulador-off-line|cerebelo como simulador off-line]]: durante el sueño, el modelo directo cerebeloso generaría las "transiciones simuladas" sobre las que la neocorteza optimiza su política de control, en paralelo al uso de Dyna como modelo del [[replay-hipocampal|replay hipocampal]]. Encarna así el polo [[control-model-based-vs-model-free|basado en modelo]] del control adaptativo.

## Citations

- [Role of cerebellum in sleep-dependent memory processes, p.8](https://doi.org/10.3389/fnsys.2023.1154489#page=8)

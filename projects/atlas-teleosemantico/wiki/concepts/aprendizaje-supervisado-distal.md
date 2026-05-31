---
page_id: aprendizaje-supervisado-distal
page_type: concept
canonical_name: Aprendizaje supervisado distal
domain_primary: life_sciences.neuroscience.computational_neuroscience
primary_domains:
- life_sciences.neuroscience.computational_neuroscience
- social_sciences.psychology.cognitive_psychology
aliases: 
- Distal supervised learning
- Jordan y Rumelhart 1992
- Controlador inverso en serie con modelo directo
relations:
- type: developed_by
  to: michael-i-jordan
  weight: canonical
- type: related_to
  to: modelo-inverso-interno-cerebeloso
  weight: canonical
- type: related_to
  to: modelo-interno-directo
  weight: canonical
- type: applied_to
  to: condicionamiento-de-parpadeo-cerebeloso
  weight: supporting
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Aprendizaje supervisado distal

## Definición

Arquitectura computacional de control motor adaptativo (Jordan y Rumelhart, 1992) en la que un controlador inverso se sitúa *en serie* con un modelo directo, y los errores se retropropagan a través del sistema compuesto para ajustar el controlador [Role of cerebellum in sleep-dependent memory processes, p.8](https://doi.org/10.3389/fnsys.2023.1154489#page=8). El "profesor" no proporciona directamente la acción correcta (señal proximal), sino la consecuencia deseada (señal distal), y el modelo directo permite traducir el error sensorial en un error sobre los comandos motores.

Estas ideas han sido muy influyentes en las teorías de replay hipocampal durante el sueño, pero rara vez se han aplicado al cerebelo (Passot et al., 2013) [Role of cerebellum in sleep-dependent memory processes, p.8](https://doi.org/10.3389/fnsys.2023.1154489#page=8). Bhattacharya et al. extienden el esquema al [[condicionamiento-de-parpadeo-cerebeloso]]: la corteza cerebelosa aprendería un modelo predictivo que entrena un controlador inverso en los núcleos cerebelosos profundos (DCN), lo que explicaría que la consolidación de este condicionamiento sea dependiente del sueño [Role of cerebellum in sleep-dependent memory processes, p.8](https://doi.org/10.3389/fnsys.2023.1154489#page=8). Articula así el [[modelo-interno-directo]] y el [[modelo-inverso-interno-cerebeloso]] dentro de un único sistema de aprendizaje.

## Citations

- [Role of cerebellum in sleep-dependent memory processes, p.8](https://doi.org/10.3389/fnsys.2023.1154489#page=8)

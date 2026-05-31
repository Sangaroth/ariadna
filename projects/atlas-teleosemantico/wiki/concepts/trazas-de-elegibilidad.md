---
page_id: trazas-de-elegibilidad
page_type: concept
canonical_name: Trazas de elegibilidad
domain_primary: life-sciences.neuroscience.computational-neuroscience
primary_domains:
- life-sciences.neuroscience.computational-neuroscience
- social-sciences.psychology.cognitive-psychology
aliases: 
- Eligibility traces
- Trazas de elegibilidad sináptica
relations:
- type: part_of
  to: aprendizaje-por-diferencia-temporal-cerebeloso
  weight: canonical
- type: related_to
  to: ltd-de-purkinje-dependiente-de-fibra-trepadora
  weight: strong
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Trazas de elegibilidad

## Definición

Una **traza de elegibilidad** (*eligibility trace*) es una marca temporal que etiqueta una sinapsis recientemente activa como candidata a ser modificada cuando llegue posteriormente una señal de aprendizaje, resolviendo el problema de asignación temporal de crédito en el aprendizaje cerebeloso [Consensus Paper: Models of Cerebellar Functions, p.13](https://doi.org/10.1007/s12311-025-01939-3#page=13).

## Forma óptima

Las trazas de elegibilidad **exponencialmente decrecientes**, asumidas por defecto en muchos modelos, son subóptimas para la predicción temporal en numerosas tareas [Consensus Paper: Models of Cerebellar Functions, p.13](https://doi.org/10.1007/s12311-025-01939-3#page=13). Estudios in vitro revelan que el cerebelo **optimiza** la forma de la traza por dos vías: mediante una señal de fibra trepadora de "perturbación" que implementa un descenso de gradiente estocástico, o mediante una elegibilidad concentrada a un retraso fijo que coincide con el retraso del feedback sensorial [Consensus Paper: Models of Cerebellar Functions, p.13](https://doi.org/10.1007/s12311-025-01939-3#page=13).

## Relevancia

Las trazas de elegibilidad son el ingrediente que permite al cerebelo asociar una señal de error de fibra trepadora con las sinapsis de fibra paralela responsables de un evento ocurrido en el pasado, y son por tanto un componente esencial del [[aprendizaje-por-diferencia-temporal-cerebeloso]] y de la [[ltd-de-purkinje-dependiente-de-fibra-trepadora]].

## Citations

- [Consensus Paper: Models of Cerebellar Functions, p.13](https://doi.org/10.1007/s12311-025-01939-3#page=13)

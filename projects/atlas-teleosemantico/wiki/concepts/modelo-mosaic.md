---
page_id: modelo-mosaic
page_type: concept
canonical_name: Arquitectura MOSAIC
domain_primary: life-sciences.neuroscience.computational-neuroscience
primary_domains:
- life-sciences.neuroscience.computational-neuroscience
- life-sciences.neuroscience.cognitive-neuroscience
- social-sciences.psychology.cognitive-psychology
aliases: 
- MOSAIC
- Modular Selection and Identification for Control
- Modelo de pares forward-inverso múltiples
relations:
- type: developed_by
  to: daniel-wolpert
  weight: canonical
- type: developed_by
  to: mitsuo-kawato
  weight: canonical
- type: builds_on
  to: modelo-interno-directo
  weight: strong
- type: builds_on
  to: modelo-inverso-interno-cerebeloso
  weight: strong
- type: related_to
  to: modelos-internos-cerebelosos-modulares
  weight: strong
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Arquitectura MOSAIC

## Definición

**MOSAIC** (*Modular Selection and Identification for Control*) es un marco computacional del control motor cerebeloso que implementa múltiples pares de modelos forward-inverso operando en paralelo [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20). En él, los **modelos forward** ([[modelo-interno-directo]]) actúan como predictores que seleccionan, para cada contexto, el conjunto de modelos inversos ([[modelo-inverso-interno-cerebeloso]]) más adecuado para generar el comando motor [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20).

## Fundamento

MOSAIC extiende el modelo inverso interno de [[mitsuo-kawato]] (1987), que combinaba un controlador feedback (corteza motora) con un controlador feedforward (cerebelo) adquirido por aprendizaje a partir de señales de error transformadas de coordenadas sensoriales a motoras [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20). La organización modular del marco encaja con la evidencia de que, en movimientos oculares y de extremidad superior, el input de la célula de Purkinje se asocia a coordenadas sensoriales y su output a coordenadas motoras, apoyando la existencia de un modelo inverso [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20).

## Relevancia

MOSAIC, desarrollado por [[daniel-wolpert]] y [[mitsuo-kawato]], resuelve el problema de control en contextos variables mediante competición y selección entre módulos, anticipando los [[modelos-internos-cerebelosos-modulares]] y conectando con la idea de un cerebelo organizado en microzonas funcionalmente especializadas pero estructuralmente uniformes.

## Citations

- [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20)

---
page_id: mitsuo-kawato
page_type: author
canonical_name: Mitsuo Kawato
domain_primary: life-sciences.neuroscience.computational-neuroscience
primary_domains:
- life-sciences.neuroscience.computational-neuroscience
- computer-science.artificial-intelligence
aliases: 
- Kawato
- M. Kawato
relations:
- type: developed
  to: modelo-inverso-interno-cerebeloso
  weight: canonical
- type: developed
  to: modelo-mosaic
  weight: canonical
- type: related_to
  to: daniel-wolpert
  weight: strong
- type: related_to
  to: transicion-de-coordenadas-visuales-a-motoras
  weight: strong
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Mitsuo Kawato

## Semblanza

Mitsuo Kawato es un referente de la neurociencia computacional del control motor cerebeloso, conocido por formalizar el [[modelo-inverso-interno-cerebeloso]]. En 1987 propuso un esquema que combina un controlador feedback localizado en la corteza motora con un controlador feedforward cerebeloso adquirido por aprendizaje a partir de señales de error transformadas de coordenadas sensoriales a motoras [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20).

## Contribución

Su modelo predijo que, para movimientos oculares y de extremidad superior, el input de la célula de Purkinje se asocia a coordenadas sensoriales y su output a coordenadas motoras, apoyando empíricamente la existencia de un modelo inverso cerebeloso [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20). Junto a [[daniel-wolpert]], Kawato desarrolló posteriormente la [[modelo-mosaic|arquitectura MOSAIC]], que implementa múltiples pares de modelos forward-inverso, donde los modelos forward seleccionan el conjunto de modelos inversos más adecuado para cada contexto [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20).

## Legado

La obra de Kawato es central en la transición del cerebelo entendido como mero corrector de errores al cerebelo como sistema de modelos internos modulares, sustento computacional de la [[transicion-de-coordenadas-visuales-a-motoras]].

## Citations

- [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20)

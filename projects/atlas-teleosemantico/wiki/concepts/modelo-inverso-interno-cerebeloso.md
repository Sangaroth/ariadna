---
page_id: modelo-inverso-interno-cerebeloso
page_type: concept
canonical_name: Modelo inverso interno cerebeloso
domain_primary: life-sciences.neuroscience.computational-neuroscience
primary_domains:
- life-sciences.neuroscience.computational-neuroscience
- life-sciences.neuroscience.behavioral-neuroscience
aliases: 
- Internal inverse model
- Modelo inverso de Kawato
- Controlador feedforward cerebeloso
relations:
- type: developed_by
  to: mitsuo-kawato
  weight: canonical
- type: contrasts_with
  to: modelo-interno-directo
  weight: strong
- type: related_to
  to: transicion-de-coordenadas-visuales-a-motoras
  weight: strong
- type: part_of
  to: modelo-mosaic
  weight: strong
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Modelo inverso interno cerebeloso

## Definición

Un **modelo inverso interno** cerebeloso es una representación interna que, dado un estado o resultado sensorial deseado, computa el comando motor necesario para alcanzarlo —la operación inversa a la de un [[modelo-interno-directo]], que predice las consecuencias sensoriales de un comando dado [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20).

## Origen y evidencia

El modelo fue formalizado por [[mitsuo-kawato]] (1987), que propuso combinar un controlador feedback localizado en la corteza motora con un controlador feedforward cerebeloso adquirido por aprendizaje, alimentado por señales de error transformadas de coordenadas sensoriales a motoras [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20). La evidencia clave es que, para movimientos oculares y de extremidad superior, el input de la célula de Purkinje se asocia a coordenadas sensoriales mientras que su output se asocia a coordenadas motoras —exactamente la transformación que implementaría un modelo inverso [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20).

## Relevancia

El modelo inverso es uno de los dos componentes de la [[arquitectura MOSAIC]], donde se empareja con un modelo forward que selecciona el módulo de control adecuado. Junto al modelo directo, articula la [[transicion-de-coordenadas-visuales-a-motoras]] como problema computacional central del cerebelo.

## Citations

- [Consensus Paper: Models of Cerebellar Functions, p.20](https://doi.org/10.1007/s12311-025-01939-3#page=20)

---
page_id: aprendizaje-por-diferencia-temporal-cerebeloso
page_type: concept
canonical_name: Aprendizaje por diferencia temporal cerebeloso
domain_primary: life-sciences.neuroscience.computational-neuroscience
primary_domains:
- life-sciences.neuroscience.computational-neuroscience
- life-sciences.neuroscience.cellular-neuroscience
aliases: 
- Cerebellar temporal difference learning
- TD learning cerebeloso
- Predicción temporal cerebelosa
relations:
- type: related_to
  to: error-de-diferencia-temporal-dopaminergico
  weight: strong
- type: builds_on
  to: trazas-de-elegibilidad
  weight: canonical
- type: related_to
  to: ltd-de-purkinje-dependiente-de-fibra-trepadora
  weight: strong
- type: related_to
  to: condicionamiento-de-parpadeo-cerebeloso
  weight: weak
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Aprendizaje por diferencia temporal cerebeloso

## Definición

Según el modelo de **diferencia temporal (TD)** aplicado al cerebelo, el cerebelo predice el tiempo de eventos sensoriales futuros comparando predicciones temporalmente sucesivas [Consensus Paper: Models of Cerebellar Functions, p.12](https://doi.org/10.1007/s12311-025-01939-3#page=12). Las fibras trepadoras (CF) muestran el sello distintivo de las señales de TD-error: responden a eventos inesperados y, tras el aprendizaje, responden menos al evento predicho y más a la clave que lo anticipa [Consensus Paper: Models of Cerebellar Functions, p.12](https://doi.org/10.1007/s12311-025-01939-3#page=12).

## Componentes

El algoritmo TD cerebeloso requiere tres elementos. Las **células granulares (GC)** proveen funciones de base temporal mediante actividad de rampa que emerge durante el aprendizaje y es heterogénea en la población [Consensus Paper: Models of Cerebellar Functions, p.12](https://doi.org/10.1007/s12311-025-01939-3#page=12). Las CF aportan la **señal de error temporal**. Y las **[[trazas-de-elegibilidad]]** etiquetan qué sinapsis son candidatas a modificación; estudios in vitro revelan que el cerebelo optimiza estas trazas, ya sea mediante una señal CF de "perturbación" (descenso de gradiente estocástico) o mediante una elegibilidad a un retraso fijo que coincide con el retraso del feedback [Consensus Paper: Models of Cerebellar Functions, p.13](https://doi.org/10.1007/s12311-025-01939-3#page=13).

## Relevancia

Frente al [[error-de-diferencia-temporal-dopaminergico]], la versión cerebelosa predice el *tiempo* de los eventos más que su valor de recompensa, con errores, base temporal y trazas de elegibilidad optimizados por tarea [Consensus Paper: Models of Cerebellar Functions, p.13](https://doi.org/10.1007/s12311-025-01939-3#page=13). Constituye un puente entre la teoría del aprendizaje supervisado cerebeloso y los marcos de aprendizaje por refuerzo.

## Citations

- [Consensus Paper: Models of Cerebellar Functions, p.12](https://doi.org/10.1007/s12311-025-01939-3#page=12)
- [Consensus Paper: Models of Cerebellar Functions, p.13](https://doi.org/10.1007/s12311-025-01939-3#page=13)

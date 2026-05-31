---
page_id: aprendizaje-por-refuerzo-cerebeloso
page_type: concept
canonical_name: Aprendizaje por refuerzo cerebeloso
domain_primary: life-sciences.neuroscience.computational-neuroscience
primary_domains:
- life-sciences.neuroscience.computational-neuroscience
- life-sciences.neuroscience.behavioral-neuroscience
- social-sciences.psychology.cognitive-psychology
aliases: 
- Cerebellar reinforcement learning
- Señales de recompensa cerebelosas
- Refuerzo modular cerebeloso
relations:
- type: contrasts_with
  to: aprendizaje-supervisado-cerebeloso
  weight: strong
- type: related_to
  to: error-de-prediccion-de-recompensa
  weight: strong
- type: related_to
  to: modelo-actor-critico
  weight: strong
- type: related_to
  to: aprendizaje-por-refuerzo-ganglios-basales
  weight: strong
- type: related_to
  to: wolfram-schultz
  weight: weak
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Aprendizaje por refuerzo cerebeloso

## Definición

Frente al dogma de que el cerebelo aprende exclusivamente de forma **supervisada** ([[aprendizaje-supervisado-cerebeloso]]) bajo señales de error de la fibra trepadora, evidencia creciente apoya un **aprendizaje por refuerzo cerebeloso**: existe señalización de recompensa en las vías de entrada de fibra trepadora (CF) y de fibra musgosa (MF) de la corteza cerebelosa [Consensus Paper: Models of Cerebellar Functions, p.14](https://doi.org/10.1007/s12311-025-01939-3#page=14). En el refuerzo, las señales instructivas no indican qué acción tomar, sino que guían el aprendizaje por ensayo y error, y las neuronas dopaminérgicas del mesencéfalo reciben input directo del cerebelo [Consensus Paper: Models of Cerebellar Functions, p.14](https://doi.org/10.1007/s12311-025-01939-3#page=14).

## Señales de recompensa de la fibra trepadora

Las fibras trepadoras responden a la recompensa en animales ingenuos y a estímulos condicionados que la predicen, y estas respuestas disminuyen cuando la recompensa se espera [Consensus Paper: Models of Cerebellar Functions, p.15](https://doi.org/10.1007/s12311-025-01939-3#page=15). A diferencia de las neuronas dopaminérgicas, las CF **no** codifican predicciones peores de lo esperado con descensos de disparo, sino que codifican resultados mejores y peores con aumentos —es decir, [[error-de-prediccion-de-recompensa|errores de predicción no firmados]] [Consensus Paper: Models of Cerebellar Functions, p.15](https://doi.org/10.1007/s12311-025-01939-3#page=15).

## Refuerzo modular

Hoang y cols. emplearon Q-learning para reproducir la conducta de lamido y estimar errores de predicción de recompensa (rPE) ensayo a ensayo; la actividad de CF se correlacionó negativamente con los rPE firmados, y la distribución espacial de los módulos se alineó con los patrones de expresión de Aldolasa-C [Consensus Paper: Models of Cerebellar Functions, p.21](https://doi.org/10.1007/s12311-025-01939-3#page=21). De ahí la propuesta de que subconjuntos de células de Purkinje actúan como **actores** dependientes de contexto en un aprendizaje [[modelo-actor-critico|crítico/actor]] modular, alineado con la organización en compartimentos [Consensus Paper: Models of Cerebellar Functions, p.21](https://doi.org/10.1007/s12311-025-01939-3#page=21).

## Citations

- [Consensus Paper: Models of Cerebellar Functions, p.14](https://doi.org/10.1007/s12311-025-01939-3#page=14)
- [Consensus Paper: Models of Cerebellar Functions, p.15](https://doi.org/10.1007/s12311-025-01939-3#page=15)
- [Consensus Paper: Models of Cerebellar Functions, p.21](https://doi.org/10.1007/s12311-025-01939-3#page=21)

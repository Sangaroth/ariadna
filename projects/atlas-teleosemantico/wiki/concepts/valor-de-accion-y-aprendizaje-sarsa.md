---
page_id: valor-de-accion-y-aprendizaje-sarsa
page_type: concept
canonical_name: Valor de acción y aprendizaje SARSA
domain_primary: physical-sciences.computer-science.machine-learning
primary_domains:
- physical-sciences.computer-science.machine-learning
- life-sciences.neuroscience.behavioral-neuroscience
aliases: 
- action value
- valor Q
- Q-value
- SARSA
- advantage learning
relations:
- type: related_to
  to: error-de-prediccion-de-recompensa
  weight: canonical
- type: related_to
  to: modelo-actor-critico
  weight: associative
- type: related_to
  to: aprendizaje-por-refuerzo-ganglios-basales
  weight: canonical
- type: related_to
  to: wolfram-schultz
  weight: associative
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Valor de acción y aprendizaje SARSA

## Definición

El valor de acción es la utilidad esperada asociada no a un estado sino a tomar una acción concreta en él (el valor Q). Frente a algoritmos que solo estiman valores de estado, los modelos basados en valor Q —SARSA y advantage learning— predicen que la señal de refuerzo debería reflejar la acción específica que se va a ejecutar [Habits, Rituals, and the Evaluative Brain, p.8](https://doi.org/10.1146/annurev.neuro.29.051605.112851#page=8).

## Evidencia neural

Morris et al. (2006) mostraron que el valor de acción de una acción futura puede codificarse en el disparo de las neuronas dopaminérgicas, lo que favorece los modelos que incorporan el valor Q [Habits, Rituals, and the Evaluative Brain, p.8](https://doi.org/10.1146/annurev.neuro.29.051605.112851#page=8). Estas neuronas pueden señalar cuál de dos acciones alternas se tomará con una latencia menor a 200 ms, lo que sugiere que otra región habría codificado ya la decisión [Habits, Rituals, and the Evaluative Brain, p.8](https://doi.org/10.1146/annurev.neuro.29.051605.112851#page=8). El propio estriado es candidato a entregar la señal de valor de acción al mesencéfalo, junto al núcleo pedunculopontino, los núcleos del rafe y la habénula lateral [Habits, Rituals, and the Evaluative Brain, p.8](https://doi.org/10.1146/annurev.neuro.29.051605.112851#page=8).

## Contexto

Este hallazgo matiza la lectura estándar de las neuronas dopaminérgicas como puro [[error-de-prediccion-de-recompensa]] al estilo de [[wolfram-schultz]], ampliándola hacia la codificación de valor de acción dentro del marco del [[aprendizaje-por-refuerzo-ganglios-basales]] y del [[modelo-actor-critico]].

## Citations

- [Habits, Rituals, and the Evaluative Brain, p.8](https://doi.org/10.1146/annurev.neuro.29.051605.112851#page=8)

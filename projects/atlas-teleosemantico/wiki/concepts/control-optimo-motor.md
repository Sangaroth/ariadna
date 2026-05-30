---
page_id: control-optimo-motor
page_type: concept
canonical_name: Control óptimo motor
domain_primary: natural-sciences.computer-science.artificial-intelligence
primary_domains:
- natural-sciences.computer-science.artificial-intelligence
- natural-sciences.neuroscience.behavioral-neuroscience
aliases: 
- optimal control
- control óptimo
- Todorov y Jordan 2002
- minimización de coste
relations:
- type: related_to
  to: problema-de-los-grados-de-libertad
  weight: canonical
- type: related_to
  to: chunking-conductual
  weight: strong
- type: related_to
  to: habilidad-motora
  weight: strong
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Control óptimo motor

## Definición

El **control óptimo** es el segundo gran reto del aprendizaje de habilidades, formalizado por Todorov y Jordan (2002): la optimalidad se define por el resultado/recompensa o por minimizar un coste —por ejemplo, la trayectoria más corta o eficiente [The Striatum: Where Skills and Habits Meet, p.2](https://doi.org/10.1101/cshperspect.a021691#page=2). El paper contrasta dos vías: el cerebelo afina el movimiento mediante *feedback* online sin señal de recompensa, mientras los ganglios basales optimizan mediante *feedback* basado en refuerzo [The Striatum: Where Skills and Habits Meet, p.2](https://doi.org/10.1101/cshperspect.a021691#page=2) (véase [[aprendizaje-supervisado-cerebeloso]] y [[aprendizaje-por-refuerzo-ganglios-basales]]).

## Estimar el coste y delimitar la acción

El control óptimo requiere estimar el coste físico o neural de una acción y delimitar cuándo empieza y termina [The Striatum: Where Skills and Habits Meet, p.8](https://doi.org/10.1101/cshperspect.a021691#page=8). En monos no entrenados, los patrones de escaneo sacádico se volvieron casi óptimos mucho después de alcanzar la recompensa máxima, guiados por el coste (la distancia) (Desrochers et al. 2010), lo que muestra que la optimización del coste opera con independencia de la maximización de la recompensa [The Striatum: Where Skills and Habits Meet, p.8](https://doi.org/10.1101/cshperspect.a021691#page=8). El [[chunking-conductual|chunking]] aparece como mecanismo que hace tratable este cómputo al [[problema-de-los-grados-de-libertad|reducir los grados de libertad]].

## Citations

- [The Striatum: Where Skills and Habits Meet, p.2](https://doi.org/10.1101/cshperspect.a021691#page=2)
- [The Striatum: Where Skills and Habits Meet, p.8](https://doi.org/10.1101/cshperspect.a021691#page=8)

---
page_id: coordinador-pre-sma
page_type: concept
canonical_name: Coordinador pre-SMA entre bucles visual y motor
domain_primary: life_sciences.neuroscience
primary_domains:
- life_sciences.neuroscience
- social_sciences.psychology.cognitive_neuroscience
aliases: 
- pre-SMA
- área motora presuplementaria
- coordinador entre bucles
- pre-supplementary motor area
relations:
- type: related_to
  to: modelo-de-bucles-paralelos-visual-motor
  weight: strong
- type: related_to
  to: transicion-de-coordenadas-visuales-a-motoras
  weight: strong
- type: related_to
  to: doble-disociacion-estriado-anterior-posterior-en-secuencias
  weight: associative
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Coordinador pre-SMA entre bucles visual y motor

## Definición

La pre-SMA (área motora presuplementaria) es propuesta como un nivel intermedio entre el bucle visual y el bucle motor en el aprendizaje de secuencias, situada entre la DLPF/estriado anterior y la SMA/estriado posterior, con M1 y PMv en la salida motora [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.2](https://doi.org/10.1162/089892901750363208#page=2). En el modelo computacional, esta función intermedia se implementa como un **coordinador**.

## Función computacional

El coordinador, junto con un módulo de cinemática inversa, transforma la representación visual en salida motora dentro de la arquitectura del modelo [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.7](https://doi.org/10.1162/089892901750363208#page=7). Combina las salidas de ambos bucles para producir la salida motora final y actualiza sus conexiones mediante la regla de refuerzo guiada por la señal de recompensa [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.8](https://doi.org/10.1162/089892901750363208#page=8). Es así el sustrato mecanístico de la [[transicion-de-coordenadas-visuales-a-motoras]].

## Evidencia de su papel

Las variantes del modelo sin coordinador rinden significativamente peor en el aprendizaje (p<0.001), lo que demuestra su contribución necesaria [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.10](https://doi.org/10.1162/089892901750363208#page=10). Coherentemente, inactivar el coordinador (pre-SMA) afecta la coordinación entre los bucles visual y motor, con un efecto que difiere entre secuencias nuevas y aprendidas, reproduciendo las inactivaciones experimentales de pre-SMA [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.14](https://doi.org/10.1162/089892901750363208#page=14).

## Citations

- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.2](https://doi.org/10.1162/089892901750363208#page=2)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.7](https://doi.org/10.1162/089892901750363208#page=7)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.8](https://doi.org/10.1162/089892901750363208#page=8)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.10](https://doi.org/10.1162/089892901750363208#page=10)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.14](https://doi.org/10.1162/089892901750363208#page=14)

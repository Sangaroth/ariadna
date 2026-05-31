---
page_id: modelo-de-bucles-paralelos-visual-motor
page_type: concept
canonical_name: Modelo de bucles paralelos visual y motor para el aprendizaje de secuencias
domain_primary: social_sciences.psychology.cognitive_neuroscience
primary_domains:
- social_sciences.psychology.cognitive_neuroscience
- life_sciences.neuroscience
- social_sciences.psychology.computational_modeling
aliases: 
- bucle visual y bucle motor
- modelo de dos bucles segregados
- visual loop motor loop model
relations:
- type: developed_by
  to: parallel-cortico-basal-ganglia-visuomotor-sequences
  weight: canonical
- type: instance_of
  to: bucles-cortico-ganglios-basales
  weight: strong
- type: related_to
  to: gradiente-funcional-del-estriado
  weight: strong
- type: related_to
  to: coordinador-pre-sma
  weight: strong
- type: related_to
  to: transicion-de-coordenadas-visuales-a-motoras
  weight: strong
- type: related_to
  to: aprendizaje-por-refuerzo-ganglios-basales
  weight: strong
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Modelo de bucles paralelos visual y motor para el aprendizaje de secuencias

## Definición

Es la hipótesis de que el aprendizaje de secuencias visuomotoras descansa en dos [[bucles-cortico-ganglios-basales]] segregados que procesan la misma tarea en sistemas de coordenadas distintos y operan en paralelo [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.1](https://doi.org/10.1162/089892901750363208#page=1). El **bucle visual** involucra la corteza prefrontal dorsolateral (DLPF) y el estriado anterior; el **bucle motor** involucra el área motora suplementaria (SMA) y el estriado posterior [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.2](https://doi.org/10.1162/089892901750363208#page=2).

## Arquitectura y niveles

La pre-SMA actúa como nivel intermedio entre ambos bucles, con M1 y PMv en la salida motora [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.2](https://doi.org/10.1162/089892901750363208#page=2). El modelo implementa una red visual y una red motora con predicciones de contexto, un módulo de cinemática inversa y un coordinador que transforma la representación visual en salida motora; el aprendizaje de cada bucle reside en conjuntos de conexiones plásticas (WVC, WVI, WMC, WMI) [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.7](https://doi.org/10.1162/089892901750363208#page=7). El coordinador combina las salidas de ambos bucles para producir la salida motora final, y las conexiones se actualizan mediante una regla de refuerzo guiada por la señal de recompensa [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.8](https://doi.org/10.1162/089892901750363208#page=8).

## Complementariedad funcional

La lógica del modelo es teleológica: cada bucle existe por lo que aporta. Las coordenadas visuales y la memoria de trabajo dan ventaja para una **adquisición rápida**, mientras que las coordenadas motoras dan ventaja para un control del movimiento **más fiable y rápido** en tiempo real [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.5](https://doi.org/10.1162/089892901750363208#page=5). En la simulación, el bucle visual aprende rápido la secuencia y el bucle motor la consolida [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.9](https://doi.org/10.1162/089892901750363208#page=9).

## Evidencia de necesidad de cada componente

Variantes del modelo sin bucle visual, sin bucle motor o sin coordinador rinden peor en el aprendizaje, con diferencias estadísticamente significativas (p<0.001), lo que demuestra que cada componente contribuye de forma diferenciada [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.10](https://doi.org/10.1162/089892901750363208#page=10). La discusión sitúa el modelo frente a otras propuestas de aprendizaje secuencial y transformación visuomotora, distinguiendo los roles de DLPF, pre-SMA, SMA y los circuitos de ganglios basales [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.16](https://doi.org/10.1162/089892901750363208#page=16).

## Citations

- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.1](https://doi.org/10.1162/089892901750363208#page=1)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.2](https://doi.org/10.1162/089892901750363208#page=2)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.5](https://doi.org/10.1162/089892901750363208#page=5)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.7](https://doi.org/10.1162/089892901750363208#page=7)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.8](https://doi.org/10.1162/089892901750363208#page=8)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.9](https://doi.org/10.1162/089892901750363208#page=9)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.10](https://doi.org/10.1162/089892901750363208#page=10)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.16](https://doi.org/10.1162/089892901750363208#page=16)

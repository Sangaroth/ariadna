---
page_id: parallel-cortico-basal-ganglia-visuomotor-sequences
page_type: entity_work
canonical_name: Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences (Nakahara, Doya & Hikosaka, 2001)
domain_primary: social_sciences.psychology.cognitive_neuroscience
primary_domains:
- social_sciences.psychology.cognitive_neuroscience
- life_sciences.neuroscience
- social_sciences.psychology.computational_modeling
aliases: 
- Nakahara Doya Hikosaka 2001
- modelo de bucles paralelos visuomotores
- Parallel cortico-basal ganglia model
relations:
- type: authored_by
  to: okihide-hikosaka
  weight: canonical
- type: authored_by
  to: kenji-doya
  weight: canonical
- type: authored_by
  to: hiroyuki-nakahara
  weight: canonical
- type: develops
  to: modelo-de-bucles-paralelos-visual-motor
  weight: canonical
- type: related_to
  to: tarea-2x5-de-secuencias-visuomotoras
  weight: strong
- type: related_to
  to: aprendizaje-de-secuencias-motoras
  weight: strong
- type: related_to
  to: aprendizaje-por-refuerzo-ganglios-basales
  weight: strong
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences (Nakahara, Doya & Hikosaka, 2001)

## Naturaleza de la obra

Artículo de modelado computacional que propone que el aprendizaje de secuencias visuomotoras se sostiene en bucles córtico-ganglio-basales paralelos —uno visual y otro motor— que operan en sistemas de coordenadas distintos y se acoplan mediante una señal de predicción de recompensa de naturaleza dopaminérgica [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.1](https://doi.org/10.1162/089892901750363208#page=1). El trabajo formaliza en una red neuronal el sustrato de los [[bucles-cortico-ganglios-basales]] e instancia la idea del [[gradiente-funcional-del-estriado]] como una división de trabajo entre el estriado anterior y el posterior.

## Objetivo y alcance

El modelo busca reproducir cuantitativamente los efectos conductuales y de inactivación observados en la tarea 2×5 de Hikosaka y colaboradores en monos [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.1](https://doi.org/10.1162/089892901750363208#page=1). Reproduce la adquisición gradual de los aciertos a lo largo de los ensayos, replicando los datos de Hikosaka et al. (1995) [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.9](https://doi.org/10.1162/089892901750363208#page=9), y simula las consecuencias de bloquear selectivamente el estriado anterior, el estriado posterior, el coordinador pre-SMA o la transmisión dopaminérgica [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.12](https://doi.org/10.1162/089892901750363208#page=12).

## Contribución y arquitectura

La arquitectura combina una red visual y una red motora con sus respectivas predicciones de contexto, un módulo de cinemática inversa y un coordinador, con conexiones plásticas (WVC, WVI, WMC, WMI) que implementan el aprendizaje de cada bucle [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.7](https://doi.org/10.1162/089892901750363208#page=7). El apéndice detalla los 16 hypersets de la tarea, las ecuaciones de las redes, la cinemática inversa, la regla de aprendizaje y los parámetros de simulación [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.19](https://doi.org/10.1162/089892901750363208#page=19).

## Relevancia para el atlas

Dentro del marco teleosemántico, la obra es un caso paradigmático de cómo la *función* de un circuito —adquirir rápido versus ejecutar fiable— explica la diferenciación de sus representaciones: las coordenadas visuales sirven al descubrimiento ensayo-error y las motoras a la ejecución consolidada [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.5](https://doi.org/10.1162/089892901750363208#page=5). Conecta el pilar de afecto/percepción/acción con el de sustrato neural al naturalizar el contenido de la acción dirigida a meta en términos de [[error-de-prediccion-de-recompensa]].

## Citations

- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.1](https://doi.org/10.1162/089892901750363208#page=1)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.5](https://doi.org/10.1162/089892901750363208#page=5)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.7](https://doi.org/10.1162/089892901750363208#page=7)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.9](https://doi.org/10.1162/089892901750363208#page=9)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.12](https://doi.org/10.1162/089892901750363208#page=12)
- [Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences, p.19](https://doi.org/10.1162/089892901750363208#page=19)

---
page_id: conectividad-efectiva-y-modelado-causal-dinamico
page_type: concept
canonical_name: Conectividad efectiva y modelado causal dinámico (DCM)
domain_primary: life-sciences.neuroscience.computational-neuroscience
primary_domains:
- life-sciences.neuroscience.computational-neuroscience
- medicine.radiology.neuroimaging
- social-sciences.psychology.cognitive-psychology
aliases: 
- DCM
- dynamic causal modeling
- conectividad efectiva
- effective connectivity
relations:
- type: applied_in
  to: delineating-cortico-striatal-cerebellar-network-msl
  weight: canonical
- type: related_to
  to: sistema-cortico-cerebeloso
  weight: related
- type: related_to
  to: sistema-cortico-estriatal
  weight: related
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Conectividad efectiva y modelado causal dinámico (DCM)

## Definición

La **conectividad efectiva** designa la influencia causal y direccional que una región neural ejerce sobre otra. A diferencia de la conectividad funcional —que solo cuantifica la correlación entre series temporales—, permite inferir si una conexión es *forward*, *backward* o recíproca ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.2](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=2)). El **modelado causal dinámico (DCM)** es la técnica que estima estos parámetros: infiere los estados neuronales "ocultos" subyacentes a la señal BOLD y selecciona el modelo de conectividad más plausible mediante **selección bayesiana de modelos (BMS)** sobre la evidencia del modelo ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.4](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=4)).

## Procedimiento

Un estudio DCM especifica, para un conjunto de ROIs, las conexiones intrínsecas (endógenas), los inputs externos y los efectos moduladores que una variable experimental ejerce sobre conexiones concretas. Tras estimar cada modelo candidato, la BMS compara su evidencia; en muestras potencialmente heterogéneas se emplea BMS de **efectos aleatorios (RFX)** con muestreo de Gibbs, dado que las redes podrían no ser consistentes entre sujetos ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.5](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=5)). Como añadir o quitar un solo modelo puede invertir el ranking, la **inferencia a nivel de familia** —agrupando modelos por una característica común (input modulador, conexión modulada, arquitectura direccional)— aporta resultados más estables ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.5](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=5)).

## Relevancia para el atlas

La capacidad de adscribir *dirección* a la influencia entre nodos es lo que permite a [[delineating-cortico-striatal-cerebellar-network-msl]] decidir entre hipótesis rivales sobre el [[sistema-cortico-cerebeloso|bucle cortico-cerebeloso]] y el [[sistema-cortico-estriatal|cortico-estriatal]], distinguiendo modulación ascendente de descendente —algo que la mera coactivación no podría resolver. En estudios previos con SEM ya se había observado que la conexión cerebelo→M1 se debilita con el tiempo mientras estriado→M1 se fortalece ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.2](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=2)).

## Citations

- [Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.2](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=2)
- [Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.4](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=4)
- [Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.5](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=5)

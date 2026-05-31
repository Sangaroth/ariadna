---
page_id: copia-eferente
page_type: concept
canonical_name: Copia eferente
domain_primary: life-sciences.neuroscience.sensorimotor
primary_domains:
- life-sciences.neuroscience.sensorimotor
- life-sciences.neuroscience.systems-neuroscience
aliases: 
- efference copy
- descarga corolaria
- corollary discharge
relations:
- type: input_to
  to: modelo-interno-directo
  weight: canonical
- type: related_to
  to: filtro-de-kalman-cerebeloso
  weight: related
- type: related_to
  to: error-de-prediccion-sensorial
  weight: related
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Copia eferente

## Definición

La copia eferente es una réplica interna del comando motor que el [[modelo-interno-directo]] emplea, junto con el estado actual del cuerpo, para predecir el estado futuro resultante de la auto-acción [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.3](https://doi.org/10.3389/fnsys.2020.00019#page=3). Es el insumo que permite distinguir las consecuencias sensoriales de la propia acción de las debidas al entorno, y por ello el sustrato de la predicción sensorimotora.

## Sustrato anatómico en el cerebro-cerebelo

La copia eferente al [[cerebro-cerebelo]] tiene base anatómica en la fuerte proyección de la corteza motora primaria (M1) hacia el cerebro-cerebelo descrita por Kelly y Strick (2003) [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.9](https://doi.org/10.3389/fnsys.2020.00019#page=9). En el esquema del [[filtro-de-kalman-cerebeloso]], esta señal cortical, transmitida por las fibras musgosas vía núcleos pontinos, constituye la entrada de predicción que las células de Purkinje transforman en el estado predicho [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.9](https://doi.org/10.3389/fnsys.2020.00019#page=9).

## Papel en el aprendizaje

Al permitir computar el estado predicho, la copia eferente habilita el cálculo del [[error-de-prediccion-sensorial]] —la discrepancia entre predicción y consecuencia real— que, según el experimento de rotación visuomotora de Mazzoni y Krakauer (2006), y no el error de objetivo, es lo que impulsa la [[adaptacion-motora]] [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.3](https://doi.org/10.3389/fnsys.2020.00019#page=3).

## Citations

- [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.3](https://doi.org/10.3389/fnsys.2020.00019#page=3)
- [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.9](https://doi.org/10.3389/fnsys.2020.00019#page=9)

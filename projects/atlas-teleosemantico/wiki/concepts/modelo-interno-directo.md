---
page_id: modelo-interno-directo
page_type: concept
canonical_name: Modelo interno directo
domain_primary: life-sciences.neuroscience.motor-control
primary_domains:
- life-sciences.neuroscience.motor-control
- social-sciences.psychology.cognition
- humanities.philosophy.mind
aliases: 
- forward model
- modelo directo
- forward internal model
relations:
- type: related_to
  to: modelo-inverso-interno-cerebeloso
  weight: canonical
- type: part_of
  to: modelos-internos-para-el-control-motor
  weight: canonical
- type: related_to
  to: error-de-prediccion-sensorial
  weight: strong
- type: contrasts_with
  to: modelo-marr-albus-del-cerebelo
  weight: moderate
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Modelo interno directo

## Definición

Desde las teorías computacionales del control motor, el cerebelo funciona como un modelo interno directo que predice las consecuencias sensoriales de los comandos motores [The Errors of Our Ways: Understanding Error Representations in Cerebellar-Dependent Motor Learning, p.2](https://doi.org/10.1007/s12311-015-0685-5#page=2). El aprendizaje motor consiste en actualizar progresivamente ese modelo para minimizar errores sistemáticos [The Errors of Our Ways: Understanding Error Representations in Cerebellar-Dependent Motor Learning, p.2](https://doi.org/10.1007/s12311-015-0685-5#page=2).

## Motivación funcional

El modelo directo resuelve el problema de los retrasos de la retroalimentación sensorial, que harían inadecuado o inestable un control en lazo cerrado simple [The Errors of Our Ways: Understanding Error Representations in Cerebellar-Dependent Motor Learning, p.2](https://doi.org/10.1007/s12311-015-0685-5#page=2). Sus predicciones permiten filtrar señales sensoriales, cancelar consecuencias autogeneradas y computar el [[error-de-prediccion-sensorial|error de predicción sensorial]] [The Errors of Our Ways: Understanding Error Representations in Cerebellar-Dependent Motor Learning, p.3](https://doi.org/10.1007/s12311-015-0685-5#page=3).

## Evidencia y especificidad de tarea

Las señales de [[error-de-rendimiento|error de rendimiento]] específicas de la tarea presentes en las espigas simples evidencian que el cerebelo adquiere un modelo interno directo de la tarea, y no meramente del efector [The Errors of Our Ways: Understanding Error Representations in Cerebellar-Dependent Motor Learning, p.8](https://doi.org/10.1007/s12311-015-0685-5#page=8). Un modelo bien adaptado reduce la sensibilidad de las espigas simples a la información sensorial autogenerada porque las señales predictiva y de retroalimentación se cancelan [The Errors of Our Ways: Understanding Error Representations in Cerebellar-Dependent Motor Learning, p.8](https://doi.org/10.1007/s12311-015-0685-5#page=8).

## Directo, no inverso

La cinética de adaptación —constante temporal de ~30 ensayos para las espigas simples frente a ~15 para la cinemática— implica que la corteza cerebelar no opera como modelo de dinámica inversa, sino como modelo directo, con el [[modelo-inverso-interno-cerebeloso|modelo inverso]] situado en otra parte del SNC [The Errors of Our Ways: Understanding Error Representations in Cerebellar-Dependent Motor Learning, p.10](https://doi.org/10.1007/s12311-015-0685-5#page=10). Esta concepción se opone a la [[modelo-marr-albus-del-cerebelo|hipótesis de Marr-Albus-Ito]] y se enmarca en la idea del [[cerebelo-maquinaria-general-de-prediccion|cerebelo como maquinaria general de predicción]].

## Citations

- [The Errors of Our Ways: Understanding Error Representations in Cerebellar-Dependent Motor Learning, p.2](https://doi.org/10.1007/s12311-015-0685-5#page=2)
- [The Errors of Our Ways: Understanding Error Representations in Cerebellar-Dependent Motor Learning, p.3](https://doi.org/10.1007/s12311-015-0685-5#page=3)
- [The Errors of Our Ways: Understanding Error Representations in Cerebellar-Dependent Motor Learning, p.8](https://doi.org/10.1007/s12311-015-0685-5#page=8)
- [The Errors of Our Ways: Understanding Error Representations in Cerebellar-Dependent Motor Learning, p.10](https://doi.org/10.1007/s12311-015-0685-5#page=10)

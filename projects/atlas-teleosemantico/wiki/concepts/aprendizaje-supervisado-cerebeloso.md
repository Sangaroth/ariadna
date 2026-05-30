---
page_id: aprendizaje-supervisado-cerebeloso
page_type: concept
canonical_name: Aprendizaje supervisado cerebeloso
domain_primary: natural-sciences.neuroscience.behavioral-neuroscience
primary_domains:
- natural-sciences.neuroscience.behavioral-neuroscience
- natural-sciences.computer-science.artificial-intelligence
aliases: 
- cerebellar supervised learning
- aprendizaje supervisado
- señal de error de las fibras trepadoras
- Marr-Albus-Ito
relations:
- type: related_to
  to: tres-algoritmos-de-aprendizaje-cerebro
  weight: canonical
- type: related_to
  to: ltd-de-purkinje-dependiente-de-fibra-trepadora
  weight: canonical
- type: related_to
  to: modelos-internos-para-el-control-motor
  weight: strong
- type: contrasts_with
  to: aprendizaje-por-refuerzo-ganglios-basales
  weight: strong
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Aprendizaje supervisado cerebeloso

## Definición

El **aprendizaje supervisado cerebeloso** es la clase de aprendizaje en la que el cerebelo ajusta sus salidas guiado por una señal de error explícita, codificada en las fibras trepadoras procedentes de la oliva inferior [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.1](https://doi.org/10.1016/s0959-4388(00)00153-7#page=1). A diferencia del [[aprendizaje-por-refuerzo-ganglios-basales|refuerzo]], donde la señal de enseñanza es escalar y evaluativa (cuánta recompensa), aquí la señal especifica un vector de error: en qué dirección y magnitud se equivocó la salida.

## Sustrato y origen teórico

La concepción del cerebelo como sistema supervisado se remonta a Marr y Albus, e Ito mostró en la adaptación del reflejo vestíbulo-ocular que la [[ltd-de-purkinje-dependiente-de-fibra-trepadora|LTD de las sinapsis de Purkinje dependiente de fibra trepadora]] es el sustrato del aprendizaje por error [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.3](https://doi.org/10.1016/s0959-4388(00)00153-7#page=3).

## Función: modelos internos y transformaciones

Los [[modelos-internos-para-el-control-motor|modelos internos]] del cuerpo y el entorno que mejoran el control motor podrían adquirirse por aprendizaje supervisado, tomando el comando motor como entrada y el resultado sensorial como señal de enseñanza [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.3](https://doi.org/10.1016/s0959-4388(00)00153-7#page=3). En tareas concretas su firma es nítida: la adaptación de ganancia separada según el tipo de sacádico (guiado visualmente frente a guiado por memoria) es justo lo que predice un modelo supervisado cerebeloso, donde solo se modifican los pesos asociados a la señal de error retiniano [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.4](https://doi.org/10.1016/s0959-4388(00)00153-7#page=4). En el control del alcance, lo crítico de los movimientos guiados visualmente es la transformación de coordenadas visuales a motoras, un problema supervisado que el cerebelo media [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.4](https://doi.org/10.1016/s0959-4388(00)00153-7#page=4).

## Citations

- [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.1](https://doi.org/10.1016/s0959-4388(00)00153-7#page=1)
- [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.3](https://doi.org/10.1016/s0959-4388(00)00153-7#page=3)
- [Complementary roles of basal ganglia and cerebellum in learning and motor control, p.4](https://doi.org/10.1016/s0959-4388(00)00153-7#page=4)

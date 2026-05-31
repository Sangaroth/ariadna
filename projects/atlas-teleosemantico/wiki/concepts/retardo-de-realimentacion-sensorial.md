---
page_id: retardo-de-realimentacion-sensorial
page_type: concept
canonical_name: Retardo de la realimentación sensorial
domain_primary: life-sciences.neuroscience.sensorimotor
primary_domains:
- life-sciences.neuroscience.sensorimotor
- physical-sciences.mathematics.control-theory
- life-sciences.neuroscience.systems-neuroscience
aliases: 
- sensory feedback delay
- retardo de conducción nerviosa
- delay aferente
relations:
- type: motivates
  to: modelo-interno-directo
  weight: canonical
- type: related_to
  to: control-optimo-motor
  weight: related
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Retardo de la realimentación sensorial

## Definición y motivación funcional

El retardo de la realimentación sensorial es la latencia inevitable entre un estímulo y la llegada de su señal aferente al córtex; constituye la justificación funcional primaria de por qué el sistema nervioso necesita un [[modelo-interno-directo]] que prediga el estado del cuerpo en lugar de depender del feedback real [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.2](https://doi.org/10.3389/fnsys.2020.00019#page=2). Las señales visuales, por ejemplo, alcanzan V1 unos 30 ms y el córtex parietal unos 80 ms tras el estímulo (Schmolesky et al., 1998) [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.2](https://doi.org/10.3389/fnsys.2020.00019#page=2).

## Determinante físico

El factor dominante del retardo es la conducción nerviosa, que escala con el tamaño corporal: va de ~10 ms en una musaraña a ~100 ms en un elefante [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.2](https://doi.org/10.3389/fnsys.2020.00019#page=2). Esta restricción biofísica es la presión selectiva que el órgano predictivo resuelve.

## Consecuencia para el control

El control por realimentación basado en estados pasados produce movimientos oscilatorios e inestables cuando el retardo es del orden de la constante de tiempo de la planta controlada [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.2](https://doi.org/10.3389/fnsys.2020.00019#page=2). El modelo directo evita esta inestabilidad al sustituir el estado retardado por un estado predicho a partir del estado actual y la [[copia-eferente]], habilitando una realimentación interna para movimientos rápidos y estables [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.3](https://doi.org/10.3389/fnsys.2020.00019#page=3). La evidencia conductual de que el componente predictivo F1 queda solo ~60 ms por detrás del objetivo —demasiado corto para ser feedback visual— confirma que esta predicción se genera realmente en el SNC [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.7](https://doi.org/10.3389/fnsys.2020.00019#page=7).

## Citations

- [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.2](https://doi.org/10.3389/fnsys.2020.00019#page=2)
- [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.3](https://doi.org/10.3389/fnsys.2020.00019#page=3)
- [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.7](https://doi.org/10.3389/fnsys.2020.00019#page=7)

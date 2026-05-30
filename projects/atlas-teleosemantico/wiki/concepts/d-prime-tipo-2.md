---
page_id: d-prime-tipo-2
page_type: concept
canonical_name: d′ de tipo 2 (Type 2 d′)
domain_primary: social-sciences.psychology.psychophysics
primary_domains:
- social-sciences.psychology.psychophysics
aliases: 
- Type 2 d-prime
- "d' de tipo 2"
- type 2 d′
- sensibilidad d′ de tipo 2
relations:
- type: part_of
  to: teoria-deteccion-senales-tipo-2
  weight: strong
- type: contrasts_with
  to: meta-d-prime
  weight: strong
- type: contrasts_with
  to: auroc2
  weight: related
- type: discussed_in
  to: how-to-measure-metacognition
  weight: canonical
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# d′ de tipo 2 (Type 2 d′)

## Definición

El **d′ de tipo 2** es una medida de [[sensibilidad-metacognitiva]] análoga al d′ de la teoría de detección de señales de primer orden, calculada como Type 2 d′ = z(H2) − z(FA2), donde H2 y FA2 son las tasas de aciertos y falsas alarmas de tipo 2 (confianza alta asignada a juicios correctos e incorrectos, respectivamente). En principio es independiente del [[sesgo-metacognitivo]], pues separa la capacidad de discriminar juicios correctos de la tendencia a usar confianzas altas [How to measure metacognition, p.3](https://doi.org/10.3389/fnhum.2014.00443#page=3).

## Por qué falla

Su validez depende del supuesto, heredado de la [[teoria-deteccion-senales-tipo-2]], de distribuciones gaussianas de igual varianza. Aceptable en tipo 1, el supuesto es muy problemático en tipo 2: Galvin et al. (2003) demostraron que, si se cumple la igualdad de varianzas en tipo 1, las distribuciones relevantes de tipo 2 resultan de varianza distinta y no gaussianas. En consecuencia, Evans y Azzopardi (2007) mostraron que la implementación del d′ de tipo 2 de Kunimoto et al. (2001) queda confundida por cambios en el sesgo, justo lo que la medida pretendía evitar [How to measure metacognition, p.3](https://doi.org/10.3389/fnhum.2014.00443#page=3).

## Lugar en la taxonomía de medidas

El d′ de tipo 2 ocupa un escalón intermedio en la progresión de medidas revisada por Fleming y Lau: supera a las [[medidas-correlacionales-phi-gamma]] al intentar aislar el sesgo, pero es inferior al [[auroc2]] (no paramétrico) y, sobre todo, al [[meta-d-prime]], que evita el supuesto gaussiano falso aprovechando que el rendimiento de tipo 1 restringe el máximo de tipo 2 [How to measure metacognition, p.3](https://doi.org/10.3389/fnhum.2014.00443#page=3).

## Citations

- [How to measure metacognition, p.3](https://doi.org/10.3389/fnhum.2014.00443#page=3)

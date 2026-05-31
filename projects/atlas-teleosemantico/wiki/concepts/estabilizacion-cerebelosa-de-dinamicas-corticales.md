---
page_id: estabilizacion-cerebelosa-de-dinamicas-corticales
page_type: concept
canonical_name: Estabilización cerebelosa de dinámicas corticales
domain_primary: physical-sciences.computer-science.computational-neuroscience
primary_domains:
- physical-sciences.computer-science.computational-neuroscience
- life-sciences.neuroscience.systems-neuroscience
- physical-sciences.mathematics.dynamical-systems
aliases: 
- cerebelo como red feedforward estabilizadora
- control de dinámicas caóticas corticales
- analogía FORCE cerebelosa
relations:
- type: related_to
  to: transformacion-cerebelosa-universal
  weight: canonical
- type: related_to
  to: filtro-de-kalman-cerebeloso
  weight: related
- type: property_of
  to: cerebro-cerebelo
  weight: related
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Estabilización cerebelosa de dinámicas corticales

## Hipótesis

Rol computacional especulado del bucle cerebro-cerebeloso: el cerebelo domaría la dinámica caótica del córtex prediciendo su actividad esperada. El córtex cerebral se modela como una red neuronal recurrente —flexible pero propensa a inestabilidad caótica— y el cerebelo como una red feedforward —estable, dependiente solo de las entradas actuales— [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.11](https://doi.org/10.3389/fnsys.2020.00019#page=11). El cerebelo "copiaría" y estabilizaría la dinámica cortical de forma análoga al algoritmo FORCE (Sussillo y Abbott, 2009) [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.12](https://doi.org/10.3389/fnsys.2020.00019#page=12).

## Base teórica

Una red feedforward de más de dos capas puede aproximar cualquier mapeo continuo, base teórica de la [[transformacion-cerebelosa-universal]] de Schmahmann [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.11](https://doi.org/10.3389/fnsys.2020.00019#page=11). Las redes recurrentes y feedforward son computacionalmente equivalentes (backpropagation-through-time; descomposición de Schur), y la arquitectura feedforward ofrece la ventaja de una computación rápida de un solo paso [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.12](https://doi.org/10.3389/fnsys.2020.00019#page=12).

## Apoyo empírico y preguntas abiertas

Wagner et al. (2019) hallaron que las células piramidales de capa 5 del neocórtex y las granulares cerebelosas comparten características de codificación de tarea, lo que apoya la propagación de dinámicas neurales compartidas entre ambas estructuras [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.12](https://doi.org/10.3389/fnsys.2020.00019#page=12). Quedan abiertas dos cuestiones: cómo utiliza el córtex la actividad predictiva cerebelosa y cómo la dinámica lineal del cerebelo aproxima la dinámica no lineal del sistema musculoesquelético [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.12](https://doi.org/10.3389/fnsys.2020.00019#page=12).

## Citations

- [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.11](https://doi.org/10.3389/fnsys.2020.00019#page=11)
- [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.12](https://doi.org/10.3389/fnsys.2020.00019#page=12)

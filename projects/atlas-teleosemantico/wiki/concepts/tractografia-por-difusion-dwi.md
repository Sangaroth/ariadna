---
page_id: tractografia-por-difusion-dwi
page_type: concept
canonical_name: Tractografía por imagen ponderada en difusión (DWI)
domain_primary: life_sciences.neuroscience.neuroimaging
primary_domains:
- life_sciences.neuroscience.neuroimaging
- life_sciences.neuroscience
aliases: 
- DWI tractography
- tractografía probabilística
- diffusion-weighted imaging
relations:
- type: related_to
  to: anisotropia-fraccional
  weight: canonical
- type: related_to
  to: sustancia-blanca-talamo-cortical
  weight: strong
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Tractografía por imagen ponderada en difusión (DWI)

## Definición

Técnica de neuroimagen que reconstruye los fascículos de sustancia blanca a partir de la difusión anisótropa del agua a lo largo de los axones. En este estudio se usó para reconstruir los fascículos del bucle cortico-estriato-pálido-tálamo-cortical en jóvenes y mayores ([Thalamo-Cortical White Matter Underlies Motor Memory Consolidation via Modulation of Sleep Spindles in Young and Older Adults, p.3](https://doi.org/10.1016/j.neuroscience.2018.12.049#page=3)).

## Procedimiento

La DWI se adquirió a 3T con resolución isotrópica de 2,0 mm a lo largo de 64 direcciones independientes y b-value de 1000 s/mm², con fieldmaps para corregir la distorsión por inhomogeneidades de campo ([Thalamo-Cortical White Matter Underlies Motor Memory Consolidation via Modulation of Sleep Spindles in Young and Older Adults, p.8](https://doi.org/10.1016/j.neuroscience.2018.12.049#page=8)). Las ROIs corticales (M1 en el giro precentral, SMA y PM) se delimitaron con White Matter Query Language y la región de la mano mediante el «hand knob»; como ROI estriatal se usó el putamen post-comisural y como ROI talámico el [[nucleo-ventral-lateral-del-talamo|núcleo VL]] ([Thalamo-Cortical White Matter Underlies Motor Memory Consolidation via Modulation of Sleep Spindles in Young and Older Adults, p.8](https://doi.org/10.1016/j.neuroscience.2018.12.049#page=8)). Se realizó tractografía probabilística con restricción anatómica, generando 5000 streamlines por fascículo en el hemisferio derecho (contralateral), y se computó un centroide submuestreado a 20 puntos equidistantes para extraer perfiles de FA a lo largo del tracto ([Thalamo-Cortical White Matter Underlies Motor Memory Consolidation via Modulation of Sleep Spindles in Young and Older Adults, p.9](https://doi.org/10.1016/j.neuroscience.2018.12.049#page=9)).

## Limitaciones

La resolución de la tractografía (8 mm³) es mucho mayor que la membrana axonal (1–15 µm), lo que impide seguir fibras individuales, y existe solapamiento considerable entre haces tálamo-corticales, cortico-estriatales y cortico-espinales en corona radiata y cápsula interna ([Thalamo-Cortical White Matter Underlies Motor Memory Consolidation via Modulation of Sleep Spindles in Young and Older Adults, p.20](https://doi.org/10.1016/j.neuroscience.2018.12.049#page=20)).

## Citations

- [Thalamo-Cortical White Matter Underlies Motor Memory Consolidation via Modulation of Sleep Spindles in Young and Older Adults, p.3](https://doi.org/10.1016/j.neuroscience.2018.12.049#page=3)
- [Thalamo-Cortical White Matter Underlies Motor Memory Consolidation via Modulation of Sleep Spindles in Young and Older Adults, p.8](https://doi.org/10.1016/j.neuroscience.2018.12.049#page=8)
- [Thalamo-Cortical White Matter Underlies Motor Memory Consolidation via Modulation of Sleep Spindles in Young and Older Adults, p.9](https://doi.org/10.1016/j.neuroscience.2018.12.049#page=9)
- [Thalamo-Cortical White Matter Underlies Motor Memory Consolidation via Modulation of Sleep Spindles in Young and Older Adults, p.20](https://doi.org/10.1016/j.neuroscience.2018.12.049#page=20)

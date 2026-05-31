---
page_id: filtro-de-kalman-cerebeloso
page_type: concept
canonical_name: Filtro de Kalman cerebeloso
domain_primary: physical-sciences.computer-science.computational-neuroscience
primary_domains:
- physical-sciences.computer-science.computational-neuroscience
- life-sciences.neuroscience.systems-neuroscience
- physical-sciences.mathematics.control-theory
aliases: 
- correspondencia cerebelo-filtro de Kalman
- Kalman filter cerebellar implementation
relations:
- type: implements
  to: modelo-interno-directo
  weight: canonical
- type: part_of
  to: control-optimo-motor
  weight: canonical
- type: located_in
  to: cerebro-cerebelo
  weight: canonical
- type: related_to
  to: copia-eferente
  weight: related
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Filtro de Kalman cerebeloso

## Definición

Hipótesis según la cual la transformación que el circuito cerebeloso realiza de las fibras musgosas (MFs) a las células del núcleo dentado (DNCs) implementa las ecuaciones de un filtro de Kalman: las células de Purkinje (PCs) computan el estado predicho (predicción), los DNCs integran predicción y feedback sensorial (filtrado), y la salida de los DNCs predice la entrada futura de las MFs (predicción cerebelosa) [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.6](https://doi.org/10.3389/fnsys.2020.00019#page=6). Es la realización mecanística del [[modelo-interno-directo]] dentro del marco del [[control-optimo-motor]] [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.3](https://doi.org/10.3389/fnsys.2020.00019#page=3).

## Evidencia electrofisiológica

Del análisis de 94 MFs, 83 PCs y 73 DNCs registrados en mono, una suma lineal ponderada de MFs reconstruyó las tasas de PCs y DNCs de forma más parsimoniosa que modelos de umbral, cuadráticos o FIR, lo que implica una computación cerebelosa más lineal de lo supuesto [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.6](https://doi.org/10.3389/fnsys.2020.00019#page=6). Las tasas de las MFs en t+t1 se predijeron como suma lineal ponderada de los DNCs en t, significativamente frente a datos sustituto, confirmando que la salida actual del órgano contiene información predictiva de su entrada futura [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.6](https://doi.org/10.3389/fnsys.2020.00019#page=6).

## Requisito morfológico de doble entrada

Un filtro de Kalman exige dos entradas separadas: una MF desde el córtex cerebral (vía núcleos pontinos, PN) que aporta la predicción —la [[copia-eferente]]— y otra MF que aporta el feedback sensorial para el filtrado [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.9](https://doi.org/10.3389/fnsys.2020.00019#page=9). La anatomía cumple el requisito: Kelly y Strick (2003) hallaron una fuerte proyección de M1 al cerebro-cerebelo, Na et al. (2019) que las MFs de PN apenas colateralizan al dentado, y Wu et al. (1999) que las MFs del núcleo reticular lateral (LRN) sí tienen abundante colateral a DN; en los datos propios, las poblaciones de MFs que reconstruyen PCs y DNCs fueron distintas (correlación media de pesos ≤0.060; p < 10⁻⁵) [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.9](https://doi.org/10.3389/fnsys.2020.00019#page=9).

## Extensión al dominio cognitivo

El esquema es compatible con el cerebro-cerebelo no motor: la entrada principal de predicción puede originarse en áreas prefrontales, parietales, temporales superiores, occipitotemporales o parahipocampales vía PN, mientras la entrada de filtrado requeriría una fuente con colaterales a DN, como la LRN o el núcleo reticular tegmental pontino (NRTP) [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.11](https://doi.org/10.3389/fnsys.2020.00019#page=11).

## Citations

- [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.3](https://doi.org/10.3389/fnsys.2020.00019#page=3)
- [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.6](https://doi.org/10.3389/fnsys.2020.00019#page=6)
- [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.9](https://doi.org/10.3389/fnsys.2020.00019#page=9)
- [The Cerebro-Cerebellum as a Locus of Forward Model: A Review, p.11](https://doi.org/10.3389/fnsys.2020.00019#page=11)

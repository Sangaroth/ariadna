---
page_id: delineating-cortico-striatal-cerebellar-network-msl
page_type: entity_work
canonical_name: Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning
domain_primary: life-sciences.neuroscience.cognitive-neuroscience
primary_domains:
- life-sciences.neuroscience.cognitive-neuroscience
- social-sciences.psychology.cognitive-psychology
- medicine.radiology.neuroimaging
aliases: 
- DCM de la red cortico-estriado-cerebelosa en MSL implícito
- Conectividad efectiva en la SRTT implícita
relations:
- type: studies
  to: aprendizaje-de-secuencias-motoras
  weight: canonical
- type: applies
  to: tarea-de-tiempo-de-reaccion-serial
  weight: canonical
- type: applies
  to: conectividad-efectiva-y-modelado-causal-dinamico
  weight: canonical
- type: evidence_for
  to: modelo-doyon-ungerleider-de-plasticidad-motora
  weight: canonical
- type: evidence_for
  to: inhibicion-cortico-cerebelosa-en-la-automatizacion-motora
  weight: canonical
- type: related_to
  to: disociacion-temporal-estriado-cerebelo
  weight: related
- type: related_to
  to: sistema-cortico-cerebeloso
  weight: related
- type: related_to
  to: sistema-cortico-estriatal
  weight: related
- type: related_to
  to: tracto-dentato-talamo-cortical
  weight: related
sources_count: 1
review_status: stub_in_session
schema_version: 1.0.0
status: stub_in_session
---

# Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning

## Definición

Estudio de neuroimagen funcional que aplica el [[conectividad-efectiva-y-modelado-causal-dinamico|modelado causal dinámico (DCM)]] sobre datos de fMRI de una [[tarea-de-tiempo-de-reaccion-serial]] (SRTT) para caracterizar las interacciones dinámicas y direccionales dentro de la red cortico-estriado-cerebelosa que media el [[aprendizaje-de-secuencias-motoras]] implícito ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.1](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=1)). El MSL se define como la mejora gradual del rendimiento mediante la repetición de un patrón serial de pulsaciones de dedos, con una implicación estriatal más pronunciada en su forma implícita que en la explícita ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.1](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=1)).

## Marco teórico

El trabajo se sitúa en el [[modelo-doyon-ungerleider-de-plasticidad-motora|modelo de Doyon y Hikosaka]], según el cual el [[sistema-cortico-cerebeloso|bucle cortico-cerebeloso]] se recluta en la [[fases-del-aprendizaje-motor|fase temprana]] de mejora rápida y la actividad se desplaza al [[sistema-cortico-estriatal|circuito cortico-estriatal]] a medida que el rendimiento se automatiza en la fase tardía ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.1](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=1)); ver [[disociacion-temporal-estriado-cerebelo]]. En este reparto, el estriado aprendería asociaciones predictivas entre movimientos mientras el cerebelo construye un modelo interno óptimo y M1 retiene la memoria motora ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.1](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=1)). La evidencia previa muestra que el cerebelo anterior se activa temprano y decrece con el aprendizaje, mientras el estriado aumenta su actividad y su disfunción (Parkinson) produce déficit en la adquisición de secuencias ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.2](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=2)).

## Diseño

De 25 sujetos sanos, 17 fueron analizados finalmente mediante DCM ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.2](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=2)). La SRTT incorporó un remapeo visuo-motor ensayo a ensayo (Rose et al., 2011) para de-correlacionar el dominio motor del perceptivo, de modo que los efectos de aprendizaje observados pudieran atribuirse únicamente al dominio motor ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.2](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=2)). Cada sesión alternaba tres bloques de secuencia (SEQ) y tres aleatorios (RND) con una secuencia oculta de 12 elementos (5-4-1-4-2-6-3-6-1-3-5-2) e intervalo inter-estímulo de 1.5 s para evitar la conciencia explícita ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.3](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=3)). Los datos BOLD se adquirieron en un escáner Philips Achieva 3T, en 4 sesiones de 284 volúmenes ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.3](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=3)).

## Análisis y modelo ganador

Se extrajeron series temporales de seis ROIs (M1, putamen y cerebelo bilaterales) y se comparó primero un conjunto de 8 modelos de conexiones intrínsecas mediante BMS de efectos fijos, y luego 22 modelos que variaban en input modulador (rendimiento vs aprendizaje), circuito modulado y direccionalidad ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.4](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=4)). Para estabilizar la selección se usó BMS de efectos aleatorios con muestreo de Gibbs e inferencia a nivel de familia ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.5](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=5)). El modelo ganador (p_ex = 0.33) tenía inputs al cerebelo bilateral y conexiones recíprocas intra-hemisferio, y en él el aprendizaje modulaba las conexiones backward de M1 a cerebelo, superando al modelo Pu→M1 por un factor de Bayes de 1.6·10⁷ ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.5](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=5)). La inferencia de familias confirmó que los modelos modulados por aprendizaje (0.91) superaban a los de rendimiento (0.09), que la arquitectura backward era superior y que las conexiones cerebelo–M1 superaban a las putamen–M1 ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.5](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=5)).

## Hallazgos

Conductualmente, los tiempos de reacción fueron más rápidos en bloques de secuencia que aleatorios en las sesiones 2–4, sin que los sujetos reportaran conciencia de la estructura ni superaran el azar en la tarea de completado (16.7% de aciertos frente a un azar del 20%), indicando aprendizaje implícito puro ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.5](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=5)). Las conexiones endógenas de cerebelo a M1 y a putamen fueron positivas y significativas, mientras que el aprendizaje modulaba negativamente las conexiones M1→cerebelo en la sesión 2, cuando los RT comenzaron a divergir ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.6](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=6)). La interpretación central es que M1 ejerce un efecto inhibitorio sobre el cerebelo que reduce su actividad al consolidarse la secuencia —ver [[inhibicion-cortico-cerebelosa-en-la-automatizacion-motora]]—, posiblemente reflejando un procesamiento reducido de errores de predicción una vez aprendido el patrón ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.8](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=8)). El predominio del bucle cortico-cerebeloso sobre el cortico-estriatal se atribuye a que los sujetos permanecieron en la fase temprana sin alcanzar la asíntota de aprendizaje ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.7](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=7)).

## Limitaciones

No se pudo desacoplar si la modulación M1→cerebelo es específica del aprendizaje motor o del mantenimiento de mapeos estímulo-respuesta, el espacio de modelos era restringido frente a un enfoque data-driven, y el bajo tamaño muestral impidió comparar "buenos" y "malos" aprendices o hallar correlaciones con el rendimiento ([Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.8](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=8)).

## Citations

- [Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.1](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=1)
- [Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.2](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=2)
- [Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.3](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=3)
- [Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.4](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=4)
- [Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.5](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=5)
- [Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.6](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=6)
- [Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.7](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=7)
- [Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning, p.8](https://doi.org/10.1016/j.neuroimage.2014.03.004#page=8)

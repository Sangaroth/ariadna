---
source_id: "doi:10.1016/j.neuroimage.2014.03.004"
source_type: paper
title: Delineating the cortico-striatal-cerebellar network in implicit motor sequence learning
generated_at: 2026-05-30T21:38:55+00:00
---

- p.1 🧠 Las redes cortico-estriado-cerebelosas median el aprendizaje motor de secuencias

  - El aprendizaje motor de secuencias (MSL) se define como la mejora gradual del rendimiento mediante la repetición de un patrón serial,
  - La tarea de tiempo de reacción serial (SRTT) es un método establecido para estudiar el MSL implícito mediante secuencias de pulsaciones de dedos,
  - Estudios previos muestran que la implicación estriatal es más pronunciada en el MSL implícito que en el explícito,
  - Se busca estudiar las interacciones dinámicas en circuitos cortico-estriatales y cortico-cerebelosos mediante modelado causal dinámico (DCM) sobre fMRI de la SRTT,

- p.1 🔄 Modelo de cambio temporal: del circuito cortico-cerebeloso al cortico-estriatal

  - El MSL se divide en una fase temprana de mejora rápida y una fase tardía de ganancias a lo largo de varias sesiones,
  - La actividad en corteza motora, parietal y cerebelo disminuye con el aprendizaje, mientras el estriado se vuelve más activo en la fase tardía,
  - El modelo de Doyon y Hikosaka propone que la red cortico-cerebelosa se recluta en la fase temprana y la actividad se desplaza al circuito cortico-estriatal cuando el rendimiento es más automático,
  - El estriado aprende asociaciones predictivas entre movimientos, mientras el cerebelo crea un modelo interno óptimo y M1 retiene la memoria motora,

- p.2 🌐 Evidencia experimental del papel de cerebelo, estriado y M1 en el MSL

  - El cerebelo anterior se activa temprano cuando se establece la memoria motora y su actividad decrece con el aprendizaje, dependiendo de las demandas de mapeo estímulo-respuesta (S–R),
  - El estriado aumenta su actividad con el aprendizaje, sugiriendo un papel en almacenamiento y retención; pacientes con disfunción estriatal (Parkinson) muestran déficit al adquirir secuencias,
  - Circuitos estriatonigral (directo) y estriatopalidal (indirecto) se activan en el aprendizaje de secuencias en ratones, con neuronas que codifican inicio, terminación y concatenación en chunks,
  - La estimulación de M1 (TMS/TBS inhibitoria) interrumpe la consolidación temprana, mientras la tDCS de M1 facilita el aprendizaje y la retención a largo plazo,

- p.2 🔗 El DCM permite inferir directionalidad de la conectividad efectiva

  - Estudios previos con SEM mostraron que la conexión cerebelo→M1 se debilita con el tiempo mientras estriado→M1 se fortalece,
  - El DCM, a diferencia de la conectividad funcional, permite inferir la direccionalidad (forward, backward o recíproca) de las conexiones,
  - Se predicen efectos moduladores negativos en la conectividad M1-cerebelo al disminuir la activación cerebelosa durante el aprendizaje,
  - Se predicen efectos moduladores positivos del aprendizaje sobre la conectividad entre M1 y putamen según el modelo de Doyon,

- p.2 🧪 Diseño de la muestra y de la SRTT con desacople motor-perceptivo

  - 25 sujetos sanos participaron; tras exclusiones, 17 sujetos se analizaron finalmente mediante DCM,
  - En la SRTT los sujetos responden con pulsación de tecla a una clave visual, aprendiendo implícitamente un patrón oculto y volviéndose más rápidos en los ensayos secuenciales,
  - Se implementó una SRTT con remapeo visuo-motor ensayo a ensayo (Rose et al., 2011) para de-correlacionar el dominio motor del perceptivo,
  - Así los efectos de aprendizaje observados pueden atribuirse únicamente al dominio motor,

- p.3 🎨 Paradigma experimental y tarea de completado para evaluar conciencia explícita

  - Cada sesión contenía seis bloques alternados: tres de secuencia (SEQ) y tres de material aleatorio (RND), con una secuencia oculta de 12 elementos (5-4-1-4-2-6-3-6-1-3-5-2),
  - El intervalo inter-estímulo se mantuvo en 1.5 s para evitar la conciencia explícita de la secuencia subyacente,
  - Tras la SRTT, una tarea de completado con 30 ensayos evaluó el conocimiento explícito, diferenciando respuestas correctas y correctas aseguradas,
  - Los datos de fMRI (BOLD, T2*) se recogieron con un escáner Philips Achieva de 3T en 4 sesiones de 284 volúmenes cada una,

- p.4 📐 Especificación del DCM y selección bayesiana de modelos

  - El DCM infiere los estados neuronales "ocultos" y selecciona un modelo "ganador" mediante selección bayesiana de modelos (BMS) sobre la evidencia del modelo,
  - Se extrajeron series temporales de seis ROIs (M1, putamen y cerebelo bilaterales) de voxels significativos en el contraste tarea > baseline,
  - En el primer paso se compararon 8 modelos de conexiones intrínsecas con inputs a CB o Pu mediante BMS de efectos fijos (FFX),
  - En el segundo paso se probaron 22 modelos que variaban según: input modulador (rendimiento vs aprendizaje), circuito modulado (cortico-estriatal/cortico-cerebeloso/ambos) y direccionalidad (forward/backward/recíproca),

- p.5 ⚖️ Inferencia a nivel de familia para estabilizar la selección de modelos

  - Se aplicó BMS de efectos aleatorios (RFX) con muestreo de Gibbs (2e6 muestras) porque las redes de MSL podrían no ser consistentes entre sujetos,
  - La inferencia a nivel de familia se usó para obtener resultados más estables, ya que añadir o quitar un modelo puede invertir el ranking,
  - Se definieron tres familias: tarea vs aprendizaje (F1), conexión modulada pu–M1/CB–M1/ambas (F2) y arquitectura forward/backward/recíproca (F3),
  - Se evaluó la significancia de las conexiones intrínsecas y moduladoras con test de Wilcoxon (p<0.05, corrección de Bonferroni),

- p.5 📊 Resultados conductuales: aprendizaje implícito sin conciencia explícita

  - Los RTs disminuyeron con las sesiones y fueron más rápidos en bloques de secuencia que aleatorios, con diferencias significativas en las sesiones 2–4 pero no en la 1,
  - La interacción sesión × condición no fue significativa y la tasa de error fue muy baja (1.66%),
  - Los sujetos no reportaron conciencia de una estructura regular en la tarea,
  - En la tarea de completado la tasa mediana de respuestas correctas fue 16.7% (nivel de azar 20%) y de correctas aseguradas 3.3%, indicando ausencia de conocimiento explícito,

- p.5 🏆 El modelo ganador: el aprendizaje modula conexiones backward de M1 a cerebelo

  - El modelo óptimo de conexiones intrínsecas (modelo 7) tenía inputs al CB bilateral y conexiones recíprocas intra-hemisferio pero no inter-hemisferio,
  - En el modelo ganador (p_ex = 0.33), el aprendizaje modulaba las conexiones backward de M1 a CB bilateralmente,
  - El siguiente modelo (Pu→M1) era inferior con un factor de Bayes de 1.6·10⁷, una diferencia muy fuerte,
  - La inferencia de familias mostró que los modelos modulados por aprendizaje (p_ex = 0.91) superaban a los de tarea (p_ex = 0.09), que la arquitectura backward era superior, y que las conexiones CB–M1 superaban a las Pu–M1,

- p.6 🔢 Parámetros del modelo: conexiones intrínsecas positivas CB→M1 y modulación negativa M1→CB

  - Las conexiones endógenas de CB a M1 y de CB a Pu bilaterales fueron positivas y significativas entre sujetos,
  - Las conexiones de M1 a CB fueron moduladas negativamente por el aprendizaje en la sesión 2 (cuando los RTs empezaron a diferir), y en sesión 3 solo en lM1→rCB,
  - Las conexiones intrínsecas de M1 a CB fueron cercanas a cero en la mayoría de sujetos,
  - No se pudieron analizar diferencias entre "buenos" y "malos" aprendices por bajo tamaño muestral, ni se hallaron correlaciones entre rendimiento y parámetros,

- p.7 💬 Discusión: el bucle cortico-cerebeloso domina en el MSL implícito temprano

  - M1 ejerce un efecto inhibitorio sobre el cerebelo, causando su descenso de actividad con el aprendizaje,
  - Los modelos con modulación M1–putamen fueron inferiores a los de modulación M1–cerebelo, destacando el papel distintivo del bucle cortico-cerebeloso,
  - Los sujetos no alcanzaron la asíntota de aprendizaje, permaneciendo en la fase temprana, lo que explicaría el dominio cortico-cerebeloso sobre el cortico-estriatal,
  - Es la primera vez que se investigan cambios de conectividad efectiva en esta red específicamente relacionados con el aprendizaje y no con el rendimiento motor,

- p.7 🧬 El papel del cerebelo: conectividad anatómica y depresión a largo plazo

  - El ROI cerebeloso (lóbulos V/VI del cerebelo anterior) corresponde al área de la mano, fuertemente conectada con el área de la mano en M1 vía núcleos profundos y tálamo,
  - La calidad estructural del tracto dentato-tálamo-cortical correlaciona con la mejora conductual en el timing del movimiento (Schulz et al., 2014),
  - El descenso de la señal BOLD cerebelosa podría reflejar depresión a largo plazo de conexiones sinápticas, propuesta como mecanismo de aprendizaje cerebeloso (Albus, Ito, Marr),
  - El modelo predice que dañar M1 o cerebelo interrumpiría la conexión recíproca y causaría déficits en MSL, consistente con estudios de estimulación y pacientes con lesión cerebelosa,

- p.8 ⚠️ Limitaciones: especificidad al aprendizaje y espacio de modelos restringido

  - No se pudo desacoplar si la modulación M1→cerebelo es específica del aprendizaje motor o del mantenimiento de mapeos S–R y la mejora de rendimiento,
  - El modelo ganador es el mejor dentro de un conjunto limitado de regiones y podría no serlo en un enfoque data-driven con miles de modelos,
  - Cualitativamente la mejora en sesión 2 se relacionó con modulación negativa M1→cerebelo, pero cuantitativamente no hubo correlación con el rendimiento,
  - El bajo tamaño muestral impidió comparar "buenos" y "malos" aprendices,

- p.8 ✅ Conclusiones: M1 inhibe el cerebelo al consolidarse la secuencia

  - El MSL implícito modula la conectividad efectiva entre M1 y cerebelo bilateral, con M1 ejerciendo un efecto inhibitorio que reduce la actividad cerebelosa,
  - Se hipotetiza que esto se relaciona con un procesamiento reducido de errores de predicción en el cerebelo una vez aprendida la secuencia,
  - La interpretación a nivel molecular debe considerarse especulativa al ser menos claros los mecanismos de inhibición en la señal BOLD,
  - Estudios futuros electrofisiológicos, de daño cerebeloso o en poblaciones con déficits (adultos mayores) beneficiarían la comprensión del papel cerebeloso,

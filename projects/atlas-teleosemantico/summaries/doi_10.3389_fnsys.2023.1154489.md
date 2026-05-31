---
source_id: "doi:10.3389/fnsys.2023.1154489"
source_type: paper
title: Role of cerebellum in sleep-dependent memory processes
generated_at: 2026-05-30T23:11:53+00:00
---

- p.1 🧠 El cerebelo, ignorado en la investigación del sueño, participa activamente en el ciclo y en la consolidación off-line

  - El cerebelo está en una posición craneal inaccesible a los electrodos EEG y su circuitería local y morfología cortical plegada producen poca señal EEG en el cuero cabelludo,
  - A pesar de contener más del 80% de las neuronas del cerebro, fue una "tierra inexplorada" en la investigación del sueño,
  - Estudios neurofisiológicos recientes muestran que el cerebelo participa en el sueño y puede modelar la arquitectura del sueño y contribuir a la consolidación off-line de la memoria (Xu et al., 2021; Torres-Herraez et al., 2022),
  - Los autores proponen un marco teórico según el cual el cerebelo sigue computando modelos internos durante el sueño para entrenar a la neocorteza,

- p.2 🌙 Las fases del sueño y la consolidación declarativa se basan en husos de sueño y reactivación hipocampal

  - El sueño se segmenta en fases REM y no-REM (esta última en tres estadios), con sincronía neuronal creciente del estadio 1 al 3,
  - El estadio 2 (45% del sueño) se define por husos de sueño (oscilaciones de 9–16 Hz) y complejos K, implicados en la consolidación de memorias procedimentales y semánticas,
  - La consolidación de memorias declarativas ocurriría mediante reactivaciones de patrones neuronales del hipocampo transferidos a la neocorteza para almacenamiento a largo plazo,
  - Las reactivaciones se acoplan en fase a los sharp wave ripples y estos a su vez a los husos de sueño,

- p.2 ✋ Las memorias procedimentales dependientes del cerebelo mejoran tras el sueño, ligadas al estadio 2

  - El cerebelo está implicado en habilidades procedimentales: adaptación del reflejo vestíbulo-ocular, condicionamiento del parpadeo y adaptación visuomotora,
  - Walker et al. (2002) demostraron mayor mejora en una tarea de tecleo secuencial tras dormir que tras igual tiempo despierto,
  - La mejora se correlacionó positiva y significativamente con la proporción de estadio 2 en el periodo de sueño intermedio,
  - El núcleo dentado muestra mayor conectividad funcional con el surco temporal superior tras el sueño, reducida tras la privación de sueño (Maquet et al., 2003),

- p.3 ⚡ La actividad cerebelosa durante el sueño y la primera detección de husos en el cerebelo

  - Estudios pioneros mostraron que la estimulación eléctrica del cerebelo podía dormir o despertar al animal, y la del pyramis y la úvula inducía husos en el EEG neocortical (Sawyer et al., 1961),
  - Las lesiones cerebelosas se asocian a mayor somnolencia diurna, menos sueño de ondas lentas y más sueño REM, con sueño fragmentado en trastornos y lesiones cerebelosas humanas,
  - Xu et al. (2021) demostraron en monos que las tasas de disparo de M1 y cerebelo se modulan de forma similar por el ciclo del sueño, con oscilaciones lentas y husos correlacionados,
  - Fue el primer informe de oscilaciones tipo huso en el cerebelo,

- p.4 🔄 El cerebelo dirige causalmente los husos de sueño hacia el tálamo y M1

  - El análisis de causalidad de Granger espectral mostró coherencia dirigida en frecuencias de huso mayor desde el cerebelo hacia el tálamo y M1, máxima durante husos neocorticales identificados,
  - Esto complica la doctrina de que los husos neocorticales surgen únicamente del tálamo (Steriade et al., 1985, 1987),
  - El impulso de husos desde el cerebelo implica que podría modelar la arquitectura del sueño, lo que explicaría por qué las lesiones cerebelosas reducen el sueño de ondas lentas,
  - Existen bucles reverberantes candidatos: el sistema olivo-cerebeloso (1–9 Hz) y las interconexiones célula granular–Golgi (10–30 Hz),

- p.4 〰️ Durante las oscilaciones de baja frecuencia el disparo cerebeloso se retrasa respecto a M1 en el sueño

  - Las oscilaciones de baja frecuencia del disparo cerebeloso durante up-states del sueño tienden a retrasarse respecto a M1, mientras que ambas áreas son síncronas durante el movimiento despierto (Xu et al., 2022),
  - Este retraso podría explicarse por el estado alterado del tálamo o por una transmisión reducida a través de los núcleos cerebelosos profundos (DCN),
  - Las células de Purkinje y las neuronas del DCN disparan más lento durante el sueño de ondas lentas,
  - Las relaciones temporales entre pares de neuronas M1-cerebelo se conservan entre sueño y movimiento, sugiriendo que la dinámica de vigilia se recapitula durante el sueño,

- p.4 🎯 El cerebelo dormido computaría modelos internos que entrenan la neocorteza vía husos

  - Los modelos internos se categorizan en modelos directos (causas→consecuencias) e inversos (consecuencias→acciones) (Wolpert y Kawato, 1998),
  - En el sueño la salida de los modelos internos cerebelosos se transmitiría vía husos de sueño, una frecuencia eficaz para impulsar plasticidad en circuitos neocorticales,
  - Se especula que la información transmitida desde el cerebelo impulsa cambios duraderos en la neocorteza durante el sueño, análogo a la consolidación episódica desde el hipocampo,

- p.7 🤖 Los modelos directos cerebelosos generan predicciones sensoriales "fictivas" para optimizar políticas de control off-line

  - Dooley et al. (2021) hallaron que la actividad del tálamo ventrolateral en ratas se sincronizaba con movimientos espontáneos, con un componente predictivo que se interrumpía al bloquear la salida cerebelosa,
  - Los autores hipotetizan que comandos motores fictivos dirigidos a metas son procesados por modelos directos cerebelosos para generar consecuencias sensoriales predichas,
  - La discrepancia entre metas fictivas y consecuencias predichas actuaría como señal de recompensa simulada (vía husos) para optimizar el controlador off-line,
  - El aprendizaje diurno almacenado en modelos directos cerebelosos se transferiría y transformaría en políticas de control mejoradas en la neocorteza,

- p.8 🧩 Arquitecturas computacionales (aprendizaje supervisado distal, Dyna) y extensión al condicionamiento del parpadeo

  - La arquitectura de aprendizaje supervisado distal (Jordan y Rumelhart, 1992) sitúa un controlador inverso en serie con un modelo directo y retropropaga errores por el sistema compuesto,
  - Estas ideas, influyentes en las teorías de replay hipocampal en sueño, rara vez se han aplicado al cerebelo (Passot et al., 2013),
  - El esquema se extiende al condicionamiento del parpadeo: la corteza cerebelosa aprendería un modelo predictivo que entrena un controlador inverso en los DCN, lo que explicaría que su consolidación sea dependiente del sueño,

- p.8 🔮 Conclusión: el cerebelo como "simulador" off-line y sus implicaciones en trastornos del neurodesarrollo

  - Quedan por aclarar si las señales cerebro-cerebelosas a frecuencias de huso influyen en el tiempo en cada fase del sueño, abordables con perturbaciones en bucle cerrado durante los husos,
  - La hipótesis del cerebelo como "simulador" off-line invita a especular sobre un papel en los sueños, con cautela por la evidencia ligada al estadio 2 frente a los sueños mayoritariamente REM,
  - El daño cerebeloso, los trastornos del sueño y la consolidación off-line deficiente se solapan en condiciones como autismo y esquizofrenia,
  - El concepto de "diásquisis del desarrollo" (Wang et al., 2014) describe cómo la disrupción cerebelosa temprana podría dañar el desarrollo de áreas corticales remotas,

---
source_id: "doi:10.1162/089892901750363208"
source_type: paper
title: Parallel Cortico-Basal Ganglia Mechanisms for Acquisition and Execution of Visuomotor Sequences
generated_at: 2026-05-30T21:44:27+00:00
---

- p.1 🧠 Mecanismos paralelos córtico-ganglios basales para adquirir y ejecutar secuencias visuomotoras

  - Propone que el aprendizaje de secuencias se sostiene en bucles córtico-ganglio-basales paralelos (visual y motor) que operan en coordenadas distintas,
  - El aprendizaje se guía por predicción de recompensa mediada por dopamina,
  - El modelo busca reproducir los efectos experimentales observados en la tarea 2×5 de Hikosaka y colaboradores,

- p.2 🔁 Dos bucles segregados: bucle visual (estriado anterior–DLPF) y bucle motor (estriado posterior–SMA)

  - El bucle visual involucra corteza prefrontal dorsolateral (DLPF) y estriado anterior,
  - El bucle motor involucra el área motora suplementaria (SMA) y estriado posterior,
  - pre-SMA actúa como nivel intermedio entre ambos bucles, con M1 y PMv en la salida motora,

- p.4 🎯 La tarea 2×5 (hyperset) como paradigma de aprendizaje secuencial

  - Cada hyperset encadena 5 sets de dos pulsaciones, completándose tras 20 ensayos correctos seguidos,
  - El sujeto parte de una tecla de inicio y debe descubrir el orden correcto por ensayo y error,
  - La secuencia puede representarse en coordenadas visuales o en coordenadas motoras,

- p.5 ⚖️ Complementariedad: adquisición rápida vs ejecución fiable y veloz

  - Las coordenadas visuales y la memoria de trabajo dan ventaja para una adquisición rápida,
  - Las coordenadas motoras dan ventaja para un control del movimiento más fiable y rápido en tiempo real,
  - Un coordinador integra ambos bucles, con una señal de predicción de recompensa (SNc/dopamina),

- p.7 🧩 Arquitectura del modelo: red visual, red motora, cinemática inversa y coordinador

  - Incluye una red visual y una red motora con sus respectivas predicciones de contexto,
  - Un módulo de cinemática inversa y un coordinador transforman la representación visual en salida motora,
  - Las conexiones plásticas (WVC, WVI, WMC, WMI) implementan el aprendizaje de cada bucle,

- p.8 📐 Formulación del coordinador, aprendizaje por refuerzo y simulación del aprendizaje

  - El coordinador combina las salidas de ambos bucles para producir la salida motora final,
  - Las conexiones se actualizan mediante una regla de refuerzo con la señal de recompensa,
  - La simulación reproduce el incremento de sets completados a lo largo de los ensayos, igual que el experimento,

- p.9 🔬 El modelo reproduce la adquisición gradual observada en monos

  - El número de ensayos con error disminuye progresivamente conforme se aprende cada hyperset,
  - El comportamiento simulado replica los datos conductuales de Hikosaka et al. (1995),
  - El bucle visual aprende rápido la secuencia y el bucle motor la consolida,

- p.10 🔀 Efecto del orden invertido y contribución de cada componente

  - Probar el orden inverso de una secuencia aprendida vuelve a elevar los errores,
  - Variantes sin bucle visual, sin bucle motor o sin coordinador rinden peor en el aprendizaje,
  - Las diferencias entre condiciones son estadísticamente significativas (p<0.001),

- p.12 🚫 Bloqueo del bucle visual / estriado anterior: deteriora lo nuevo, respeta lo aprendido

  - Bloquear el input visual o el estriado anterior perjudica el aprendizaje de secuencias nuevas,
  - Las secuencias ya aprendidas se ejecutan con escaso deterioro,
  - El patrón simulado coincide con las inactivaciones experimentales (control vs bloqueo),

- p.13 🛑 Bloqueo del bucle motor / estriado posterior / SMA: deteriora lo aprendido

  - Bloquear el input motor, el estriado posterior o la SMA perjudica la ejecución de secuencias aprendidas,
  - Las secuencias nuevas se ven menos afectadas por este bloqueo,
  - Se reproduce la doble disociación entre estriado anterior y posterior,

- p.14 🤝 Bloqueo del coordinador / pre-SMA y su papel integrador

  - Inactivar el coordinador (pre-SMA) afecta la coordinación entre bucles visual y motor,
  - El efecto difiere entre secuencias nuevas y aprendidas,
  - La simulación reproduce los resultados de las inactivaciones de pre-SMA,

- p.15 💧 Disfunción dopaminérgica: predicción de recompensa y aprendizaje de lo nuevo

  - La disfunción dopaminérgica antes del aprendizaje deteriora la adquisición de secuencias nuevas,
  - Tras el aprendizaje, el deterioro sobre secuencias aprendidas es mucho menor,
  - La señal dopaminérgica de recompensa es crítica para adquirir, no tanto para ejecutar,

- p.16 💬 Discusión: relación con otros modelos y estructuras del aprendizaje procedimental

  - Sitúa el modelo frente a otras propuestas de aprendizaje secuencial y de transformación visuomotora,
  - Discute los roles diferenciados de DLPF, pre-SMA, SMA y los circuitos de ganglios basales,
  - Enfatiza la transición de coordenadas visuales a motoras durante la consolidación,

- p.19 📑 Apéndice: especificación de la tarea y ecuaciones del modelo

  - Detalla los 16 hypersets y la estructura de los sets de la tarea 2×5,
  - Formaliza las ecuaciones de las redes, la cinemática inversa y la regla de aprendizaje,
  - Especifica los parámetros usados en las simulaciones,

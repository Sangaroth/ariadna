# Pilot v2 -- Dense vs RRF vs Dense+Reranker

**Top-K**: 5 | **Prefetch**: 20 | **Modelos**: BGE-M3 (dense+sparse) + BGE-reranker-v2-m3

Tres lanes por query: **Dense** (BGE-M3 solo), **RRF** (dense+sparse fusion), **Reranker** (dense top-20 -> cross-encoder -> top-5).
Las queries q11-q15 son **adversariales** (coloquial, paráfrasis lejanas).

---

## Resumen comparativo

| Query | Tipo | dense top-20 | dense top-5 | RRF top-5 | Reranker top-5 |
|---|---|---|---|---|---|
| q01 | natural | 1 | 1 | 1 | 1 |
| q02 | paraphrase | 1 | 1 | 1 | 1 |
| q03 | natural | 3 | 3 | 3 | 1 |
| q04 | proper_noun | 2 | 2 | 2 | 1 |
| q05 | proper_noun | 1 | 1 | 1 | 1 |
| q06 | paraphrase | 1 | 1 | 1 | 1 |
| q07 | proper_noun | 1 | 1 | 1 | 1 |
| q08 | natural | 1 | 1 | 1 | 1 |
| q09 | paraphrase | 1 | 1 | 1 | 1 |
| q10 | proper_noun | 1 | 1 | 1 | 1 |
| q11 | adversarial_colloquial | 1 | 1 | 2 | 1 |
| q12 | adversarial_paraphrase | 1 | 1 | 1 | 1 |
| q13 | adversarial_colloquial | 6 | — | 5 | 2 |
| q14 | adversarial_paraphrase | 18 | — | — | 4 |
| q15 | adversarial_colloquial | 1 | 1 | 1 | 1 |

---

## q01 -- *natural* -- psicología

> **¿qué tres pilares debe desarrollar una crianza sana en la personalidad?**

_Hipótesis: Pregunta directa con vocabulario del chunk (firmeza, seguridad, autonomía). Mide baseline._

_Posición chunk fuente_: dense20=1 | dense5=1 | RRF5=1 | reranker5=1

### Dense top-5

**1.** `0.7671` | *psicología* | luna roja sobre el varón II: "lnceIs" [04:03]  **<- chunk fuente**
   🌱 Los tres pilares de una crianza sana: firmeza, seguridad y autonomía
   - Un ambiente afectivo sano debe desarrollar firmeza, seguridad y autonomía en la personalidad
- En el hombre la firmeza va hacia la fuerza, la seguridad hacia el Eros y la autonomía hacia el dominio
- Cuando la crianza falla, firmeza, segu...

**2.** `0.5259` | *psicología* | Elisa y su CI [1:07:48]
   ⚔️ El camino del héroe masculino: dominio intelectual, físico y laboral
   - Tres pilares: ser el mejor en un hobby autónomo, en un dominio intelectual y en el trabajo
- Ejercicio físico preferiblemente de coordinación corporal (artes marciales, baile)
- Relaciones sociales amplias sin implicación emocional profun...

**3.** `0.5176` | *psicología* | Psicoanálisis de la orientación política: Dime a quién votas y te diré quién es tu madre. [12:40]
   👶 Desarrollo del yo: genética, gestación y primera infancia
   - El yo se construye con tres componentes: experiencia, desarrollo congénito/gestacional y base genética
- De los 0 a los 3 años se forma la base que determinará gran parte de la conducta futura
- De los 3 a los 8 años se desarrollan los me...

**4.** `0.5159` | *psicología* | Este es el camino [00:00]
   💪 Los cuatro pilares de la construcción de masculinidad
   - Buscar un hobby que dependa únicamente de uno mismo y mejorar en él a espaldas de todo el mundo
- Hacer deporte físico, preferiblemente combate o baile, algo que implique el cuerpo y la coordinación
- Conocer gente constantemente: relacio...

**5.** `0.5106` | *psicología* | luna roja sobre el varón II: "lnceIs" [11:37]
   🧊 Crianza súper racional o súper exigente: la masculinidad mal integrada
   - Padre frío, distante o débil que solo mide resultados y no conecta emocionalmente con el hijo
- La ausencia de madre en el hogar implica falta de conexión de intimidad y calidez femenina
- Esta combinación exige al niño desarrollar herram...

### RRF top-5

**1.** `1.0000` | *psicología* | luna roja sobre el varón II: "lnceIs" [04:03]  **<- chunk fuente**
   🌱 Los tres pilares de una crianza sana: firmeza, seguridad y autonomía
   - Un ambiente afectivo sano debe desarrollar firmeza, seguridad y autonomía en la personalidad
- En el hombre la firmeza va hacia la fuerza, la seguridad hacia el Eros y la autonomía hacia el dominio
- Cuando la crianza falla, firmeza, segu...

**2.** `0.4444` | *psicología* | T5x02: No Love Land [1:21:15]
   🧒 Edad clave del desarrollo de la personalidad: 8-12 años
   - Es cuando el yo empieza a desarrollarse y el individuo se individúa por ambigüación
- El niño descubre que los demás lo perciben de formas distintas y comienza a formar autoconcepto
- Si en esa ventana no hay base segura, los pilares de p...

**3.** `0.4167` | *psicología* | Elisa y su CI [1:07:48]
   ⚔️ El camino del héroe masculino: dominio intelectual, físico y laboral
   - Tres pilares: ser el mejor en un hobby autónomo, en un dominio intelectual y en el trabajo
- Ejercicio físico preferiblemente de coordinación corporal (artes marciales, baile)
- Relaciones sociales amplias sin implicación emocional profun...

**4.** `0.3929` | *análisis de obra* | Excalibur, El Señor de los Anillos, y el mito Católico. [44:01]
   🛡️ Las cuatro virtudes cardinales y las tres virtudes teologales
   - Prudencia, justicia, fortaleza y templanza son las virtudes cardinales que el héroe debe desarrollar
- Fe, esperanza y caridad son las virtudes teologales que solo pueden ser concedidas por Dios
- La cardinalidad representa los cuatro eje...

**5.** `0.2909` | *psicología* | Este es el camino [00:00]
   💪 Los cuatro pilares de la construcción de masculinidad
   - Buscar un hobby que dependa únicamente de uno mismo y mejorar en él a espaldas de todo el mundo
- Hacer deporte físico, preferiblemente combate o baile, algo que implique el cuerpo y la coordinación
- Conocer gente constantemente: relacio...

### Dense+Reranker top-5

**1.** `0.9995` | *psicología* | luna roja sobre el varón II: "lnceIs" [04:03]  **<- chunk fuente**
   🌱 Los tres pilares de una crianza sana: firmeza, seguridad y autonomía
   - Un ambiente afectivo sano debe desarrollar firmeza, seguridad y autonomía en la personalidad
- En el hombre la firmeza va hacia la fuerza, la seguridad hacia el Eros y la autonomía hacia el dominio
- Cuando la crianza falla, firmeza, segu...

**2.** `0.2090` | *psicología* | T5x02: No Love Land [1:21:15]
   🧒 Edad clave del desarrollo de la personalidad: 8-12 años
   - Es cuando el yo empieza a desarrollarse y el individuo se individúa por ambigüación
- El niño descubre que los demás lo perciben de formas distintas y comienza a formar autoconcepto
- Si en esa ventana no hay base segura, los pilares de p...

**3.** `0.1675` | *psicología* | Elisa y su CI [1:07:48]
   ⚔️ El camino del héroe masculino: dominio intelectual, físico y laboral
   - Tres pilares: ser el mejor en un hobby autónomo, en un dominio intelectual y en el trabajo
- Ejercicio físico preferiblemente de coordinación corporal (artes marciales, baile)
- Relaciones sociales amplias sin implicación emocional profun...

**4.** `0.0495` | *psicología* | luna roja sobre el varón II: "lnceIs" [11:37]
   🧊 Crianza súper racional o súper exigente: la masculinidad mal integrada
   - Padre frío, distante o débil que solo mide resultados y no conecta emocionalmente con el hijo
- La ausencia de madre en el hogar implica falta de conexión de intimidad y calidez femenina
- Esta combinación exige al niño desarrollar herram...

**5.** `0.0376` | *cultura y actualidad* | León XIV, y George Floyd. [1:02:08]
   🧬 La crianza sin género como generadora de esquizoipia
   - Las personas no tienen género sino sexo, orientación sexual y cognición sexuada; el sexo es polar, no un espectro
- Sin feedback de refuerzo sobre quién es el niño, este no descubre su identidad por sí mismo: el mundo nos envía mensajes s...

---

## q02 -- *paraphrase* -- psicología

> **¿cuál es la unidad mínima de aprendizaje neuronal con función biológica propia?**

_Hipótesis: Paráfrasis de 'priming' sin usar la palabra. Estresa al sparse, debería favorecer al dense._

_Posición chunk fuente_: dense20=1 | dense5=1 | RRF5=1 | reranker5=1

### Dense top-5

**1.** `0.6472` | *psicología* | El papel de la psicología en la ciencia médica. Del psicoanálisis a la neurología. [49:41]  **<- chunk fuente**
   ⚡ El priming como unidad mínima de aprendizaje con función biológica
   - El priming es la forma más elemental de aprendizaje: modificación neuronal con función biológica propia
- Se diferencia de la potenciación a largo plazo (PLP) porque requiere función biológica, no mera modificación sináptica
- La cognició...

**2.** `0.5298` | *psicología* | ¿Sueña ChatGPT con ovejas eléctricas? [1:30:22]
   💡 Inteligencia como eutaxia de la función biológica
   - La inteligencia es la eutaxia (buen orden) de la función biológica: nacer, crecer, aprender, reproducirse, enseñar y morir con recursos limitados
- Requiere tres funciones cognitivas: adaptación/equilibrio, aprendizaje/anticipación, y com...

**3.** `0.5081` | *cultura y actualidad* | La IA se sale de madre. Ética e IA parte 4 [55:41]
   🔄 Las cinco funciones biológicas: crecer, reproducirse, aprender, enseñar y morir
   - El organismo es como un ordenador con objetivos programados que cumplir secuencialmente
- Enseñar incluye desde la transmisión verbal hasta la mera transmisión genética
- El cuerpo se prepara químicamente para la muerte: la mente asume y ...

**4.** `0.5049` | *cultura y actualidad* | Tremendo lunes [1:57:06]
   🔬 Niveles de arquitectura: dónde la emulación se convierte en simulación
   - Toda emulación, al descender niveles de arquitectura, revela un punto donde aparece la diferencia ontológica
- A nivel proteínas o atómico se distingue lo artificial de lo natural: la simulación depende del nivel estructural
- La única re...

**5.** `0.5023` | *filosofía y teoría* | Teoría de la información integrada y los LLMs (Ahora sí) [1:21:25]
   🤖 Comparación de Phi entre cerebro humano y LLM
   - La Phi del cerebro es altísima: es un grafo tridimensional donde cada nodo (neurona) contiene átomos formando redes moleculares con su propia Phi
- Un LLM tiene complejidad enormemente inferior: su unidad mínima es el bit, mientras que la...

### RRF top-5

**1.** `1.0000` | *psicología* | El papel de la psicología en la ciencia médica. Del psicoanálisis a la neurología. [49:41]  **<- chunk fuente**
   ⚡ El priming como unidad mínima de aprendizaje con función biológica
   - El priming es la forma más elemental de aprendizaje: modificación neuronal con función biológica propia
- Se diferencia de la potenciación a largo plazo (PLP) porque requiere función biológica, no mera modificación sináptica
- La cognició...

**2.** `0.4583` | *psicología* | ¿Sueña ChatGPT con ovejas eléctricas? [1:30:22]
   💡 Inteligencia como eutaxia de la función biológica
   - La inteligencia es la eutaxia (buen orden) de la función biológica: nacer, crecer, aprender, reproducirse, enseñar y morir con recursos limitados
- Requiere tres funciones cognitivas: adaptación/equilibrio, aprendizaje/anticipación, y com...

**3.** `0.3958` | *psicología* | Psicología 101: Conductismo, sofisma y filosofía. [1:24:29]
   🧬 Función propia: concepto del realismo cognitivo
   - Una función propia es aquella característica de un ser vivo que existe porque proviene de servir para algo y se ha perfeccionado evolutivamente para ello
- La función propia de la piel es el aislamiento térmico e impermeable; el pelo tien...

**4.** `0.2909` | *análisis de obra* | Análisis La Llegada, (Parte uno, introducción) [1:11:28]
   🪱 Las categorías biológicas fundamentales: del nematodo a la complejidad
   - Las lombrices tienen categorías biológicas mínimas: posiciones neuronales que determinan dirección de movimiento según frío, calor u oxígeno
- Con el desarrollo de la visión, la complejidad neurológica crece exponencialmente
- Las categor...

**5.** `0.2778` | *filosofía y teoría* | Teoría de la información integrada y los LLMs (Ahora sí) [1:21:25]
   🤖 Comparación de Phi entre cerebro humano y LLM
   - La Phi del cerebro es altísima: es un grafo tridimensional donde cada nodo (neurona) contiene átomos formando redes moleculares con su propia Phi
- Un LLM tiene complejidad enormemente inferior: su unidad mínima es el bit, mientras que la...

### Dense+Reranker top-5

**1.** `0.9985` | *psicología* | El papel de la psicología en la ciencia médica. Del psicoanálisis a la neurología. [49:41]  **<- chunk fuente**
   ⚡ El priming como unidad mínima de aprendizaje con función biológica
   - El priming es la forma más elemental de aprendizaje: modificación neuronal con función biológica propia
- Se diferencia de la potenciación a largo plazo (PLP) porque requiere función biológica, no mera modificación sináptica
- La cognició...

**2.** `0.3118` | *filosofía y teoría* | Teoría de la información integrada y los LLMs (Ahora sí) [1:21:25]
   🤖 Comparación de Phi entre cerebro humano y LLM
   - La Phi del cerebro es altísima: es un grafo tridimensional donde cada nodo (neurona) contiene átomos formando redes moleculares con su propia Phi
- Un LLM tiene complejidad enormemente inferior: su unidad mínima es el bit, mientras que la...

**3.** `0.0475` | *filosofía y teoría* | Psicología 101, Del libre albedrío a la computación artificial [27:54]
   🧩 Clases cognitivas como mónadas universales lingüísticas
   - Las clases cognitivas son la mínima unidad de experiencia consciente universal, frente al qualia que es subjetivo
- Se buscará contrastar mónadas universales conocidas (universales culturales) con patrones de activación cerebral en experi...

**4.** `0.0377` | *análisis de obra* | Análisis La Llegada, (Parte uno, introducción) [1:11:28]
   🪱 Las categorías biológicas fundamentales: del nematodo a la complejidad
   - Las lombrices tienen categorías biológicas mínimas: posiciones neuronales que determinan dirección de movimiento según frío, calor u oxígeno
- Con el desarrollo de la visión, la complejidad neurológica crece exponencialmente
- Las categor...

**5.** `0.0270` | *psicología* | ¿Sueña ChatGPT con ovejas eléctricas? [1:30:22]
   💡 Inteligencia como eutaxia de la función biológica
   - La inteligencia es la eutaxia (buen orden) de la función biológica: nacer, crecer, aprender, reproducirse, enseñar y morir con recursos limitados
- Requiere tres funciones cognitivas: adaptación/equilibrio, aprendizaje/anticipación, y com...

---

## q03 -- *natural* -- psicología

> **¿qué factores funcionan como causa y consecuencia a la vez en los trastornos de conducta alimentaria?**

_Hipótesis: Natural pero expandiendo el acrónimo TCA — si sparse depende de 'TCA' literal, podría perder contra dense._

_Posición chunk fuente_: dense20=3 | dense5=3 | RRF5=3 | reranker5=1

### Dense top-5

**1.** `0.6384` | *psicología* | Proxy, Effy, los TCAs y el ego, parte final [00:01]
   🧠 Dos enfoques para entender los trastornos de conducta alimentaria
   - Los TCA pueden verse como un problema de autoimagen convertido en dinámica obsesiva con la comida
- Alternativamente, pueden entenderse como una sublimación de la culpa introyectada donde la persona se castiga a sí misma
- El enfoque psic...

**2.** `0.6232` | *psicología* | Proxy, Effy y los TCAs Primera Parte [03:31]
   🍽️ Definición de los trastornos de la conducta alimentaria (TCA)
   - Los TCA son de los trastornos más fáciles de adquirir (más adquiridos que innatos), aunque requieren una estructura ansiosa u obsesiva
- A diferencia de los trastornos de personalidad, que se forman junto a la personalidad, los TCA pueden...

**3.** `0.6100` | *psicología* | Proxy, Effy, los TCAs y el ego, parte final [04:07]  **<- chunk fuente**
   🔄 Diátesis de los TCA: causas que son a la vez consecuencias
   - No aceptarse, percibir poco control sobre la vida, ser poco habilidoso socialmente son causa y consecuencia simultánea
- Falta de espontaneidad, demasiado autocontrol, dependencia afectiva, perfeccionismo y autocrítica exagerada
- Tendenc...

**4.** `0.5778` | *psicología* | Psicología 101: Ego, autoestima y TCAs [40:07]
   📋 Diátesis de los TCAs: causas que son también consecuencias
   - No aceptarse como persona, percibir poco control, ser poco habilidoso socialmente, fracaso para expresar problemas emocionales
- Dependencia afectiva, perfeccionismo, autocrítica excesiva, baja autoestima, personalidad depresiva
- Todo es...

**5.** `0.5730` | *psicología* | Proxy, Effy y los TCAs Primera Parte [05:32]
   🔬 Diferencia entre TCA: semejanza estereotípica vs. dinámicas distintas
   - Los distintos TCA solo se parecen estereotípicamente (por fuera, en lo relacionado con comida), pero tienen dinámicas y orígenes diferentes
- La definición exige que sea una conducta ansiosa, no una conducta psicótica ni errática
- Comer ...

### RRF top-5

**1.** `0.8333` | *psicología* | Proxy, Effy, los TCAs y el ego, parte final [00:01]
   🧠 Dos enfoques para entender los trastornos de conducta alimentaria
   - Los TCA pueden verse como un problema de autoimagen convertido en dinámica obsesiva con la comida
- Alternativamente, pueden entenderse como una sublimación de la culpa introyectada donde la persona se castiga a sí misma
- El enfoque psic...

**2.** `0.8333` | *psicología* | Proxy, Effy y los TCAs Primera Parte [03:31]
   🍽️ Definición de los trastornos de la conducta alimentaria (TCA)
   - Los TCA son de los trastornos más fáciles de adquirir (más adquiridos que innatos), aunque requieren una estructura ansiosa u obsesiva
- A diferencia de los trastornos de personalidad, que se forman junto a la personalidad, los TCA pueden...

**3.** `0.3000` | *psicología* | Proxy, Effy, los TCAs y el ego, parte final [04:07]  **<- chunk fuente**
   🔄 Diátesis de los TCA: causas que son a la vez consecuencias
   - No aceptarse, percibir poco control sobre la vida, ser poco habilidoso socialmente son causa y consecuencia simultánea
- Falta de espontaneidad, demasiado autocontrol, dependencia afectiva, perfeccionismo y autocrítica exagerada
- Tendenc...

**4.** `0.2500` | *psicología* | Psicoinfluencers [50:27]
   ❓ La pregunta ausente del conductismo: qué ocurre entre consecuencia y siguiente conducta
   - El conductismo no explica el mecanismo del aprendizaje, solo lo etiqueta como refuerzo o no refuerzo
- Falta la cadena causal que conecta la consecuencia con la modificación conductual
- Ni siquiera los reptiles operan exclusivamente por ...

**5.** `0.2000` | *psicología* | Psicología 101: Ego, autoestima y TCAs [40:07]
   📋 Diátesis de los TCAs: causas que son también consecuencias
   - No aceptarse como persona, percibir poco control, ser poco habilidoso socialmente, fracaso para expresar problemas emocionales
- Dependencia afectiva, perfeccionismo, autocrítica excesiva, baja autoestima, personalidad depresiva
- Todo es...

### Dense+Reranker top-5

**1.** `0.6203` | *psicología* | Proxy, Effy, los TCAs y el ego, parte final [04:07]  **<- chunk fuente**
   🔄 Diátesis de los TCA: causas que son a la vez consecuencias
   - No aceptarse, percibir poco control sobre la vida, ser poco habilidoso socialmente son causa y consecuencia simultánea
- Falta de espontaneidad, demasiado autocontrol, dependencia afectiva, perfeccionismo y autocrítica exagerada
- Tendenc...

**2.** `0.1784` | *psicología* | Proxy, Effy, los TCAs y el ego, parte final [00:01]
   🧠 Dos enfoques para entender los trastornos de conducta alimentaria
   - Los TCA pueden verse como un problema de autoimagen convertido en dinámica obsesiva con la comida
- Alternativamente, pueden entenderse como una sublimación de la culpa introyectada donde la persona se castiga a sí misma
- El enfoque psic...

**3.** `0.1750` | *psicología* | Proxy, Effy y los TCAs Primera Parte [03:31]
   🍽️ Definición de los trastornos de la conducta alimentaria (TCA)
   - Los TCA son de los trastornos más fáciles de adquirir (más adquiridos que innatos), aunque requieren una estructura ansiosa u obsesiva
- A diferencia de los trastornos de personalidad, que se forman junto a la personalidad, los TCA pueden...

**4.** `0.1623` | *psicología* | Psicología 101: Ego, autoestima y TCAs [40:07]
   📋 Diátesis de los TCAs: causas que son también consecuencias
   - No aceptarse como persona, percibir poco control, ser poco habilidoso socialmente, fracaso para expresar problemas emocionales
- Dependencia afectiva, perfeccionismo, autocrítica excesiva, baja autoestima, personalidad depresiva
- Todo es...

**5.** `0.0557` | *psicología* | Proxy, Effy y los TCAs Primera Parte [04:02]
   ⚡ La ansiedad como motor de los TCA: ansiedad impulsiva vs. no impulsiva
   - Los TCA están causados por ansiedad en sentido impulsivo: la ansiedad genera una necesidad de conducta (ansiedad positiva/activa)
- El perfil de anorexia nerviosa es bastante diferente al de bulimia y trastorno por atracón
- El rasgo nucl...

---

## q04 -- *proper_noun* -- análisis de obra

> **la escena en Prometheus donde Elizabeth se autoextirpa la criatura con la cápsula médica de la nave**

_Hipótesis: Nombre propio (Prometheus, Elizabeth) y término específico (cápsula médica). Sparse debería dominar._

_Posición chunk fuente_: dense20=2 | dense5=2 | RRF5=2 | reranker5=1

### Dense top-5

**1.** `0.5304` | *análisis de obra* | Un Gólem llamado Prometeo [1:04:08]
   🔭 Elizabeth como síntesis de ciencia, fe y búsqueda humana de los orígenes
   - Último informe de Elizabeth: "Soy la última superviviente del Prometheus y continúo buscando"
- Representa simultáneamente la ciencia, la fe y la unión de ambas que constituye a la humanidad
- Antes de los créditos: su "hijo" cefalópodo +...

**2.** `0.4983` | *análisis de obra* | Un Gólem llamado Prometeo [51:26]  **<- chunk fuente**
   🩸 La cirugía del feto alienígena: Elizabeth como madre involuntaria que extrae su horror
   - David informa a Elizabeth que tiene un "feto de 3 meses" dentro pese a haber tenido sexo solo 10 horas antes — y no es un feto normal
- En lugar de operarla, David sugiere mantenerla en hibernación; ella escapa y usa la cápsula médica de ...

**3.** `0.4847` | *psicología* | Consideraciones sobre Olaf, la conducta motivada, y la trazabilidad del pensamiento [33:43]
   💀 El suicidio del arquitecto en Prometheus y el significado de la sustancia negra
   - El arquitecto se suicida porque no puede soportar su propia obra: la creación de la sustancia negra que aísla el mal
- El significado del inicio de Prometheus se explica al final de Alien Covenant con la frase "Me he convertido en muerte,...

**4.** `0.4834` | *análisis de obra* | Un Gólem llamado Prometeo. [21:12]
   🧬 La escena inicial de Prometheus: el ingeniero y la sustancia negra
   - Un ser proto-humano bebe una sustancia que destruye su ADN desde dentro y cae disuelto en una cascada
- De sus restos en el agua surge una nueva cadena parecida al ADN que genera células: el origen de la vida humana
- Primera polaridad ex...

**5.** `0.4691` | *análisis de obra* | Un Gólem llamado Prometeo [59:32]
   🛸 La nave de destrucción masiva: los ingenieros planeaban exterminar a la humanidad con materia oscura
   - La estructura no era una instalación científica sino una nave cargada de sustancia negra con destino la Tierra como arma química
- El plan original fracasó porque la sustancia se volvió contra los propios ingenieros durante la misión y lo...

### RRF top-5

**1.** `0.8333` | *análisis de obra* | Un Gólem llamado Prometeo [1:04:08]
   🔭 Elizabeth como síntesis de ciencia, fe y búsqueda humana de los orígenes
   - Último informe de Elizabeth: "Soy la última superviviente del Prometheus y continúo buscando"
- Representa simultáneamente la ciencia, la fe y la unión de ambas que constituye a la humanidad
- Antes de los créditos: su "hijo" cefalópodo +...

**2.** `0.8333` | *análisis de obra* | Un Gólem llamado Prometeo [51:26]  **<- chunk fuente**
   🩸 La cirugía del feto alienígena: Elizabeth como madre involuntaria que extrae su horror
   - David informa a Elizabeth que tiene un "feto de 3 meses" dentro pese a haber tenido sexo solo 10 horas antes — y no es un feto normal
- En lugar de operarla, David sugiere mantenerla en hibernación; ella escapa y usa la cápsula médica de ...

**3.** `0.4000` | *análisis de obra* | Un Gólem llamado Prometeo. [21:12]
   🧬 La escena inicial de Prometheus: el ingeniero y la sustancia negra
   - Un ser proto-humano bebe una sustancia que destruye su ADN desde dentro y cae disuelto en una cascada
- De sus restos en el agua surge una nueva cadena parecida al ADN que genera células: el origen de la vida humana
- Primera polaridad ex...

**4.** `0.3500` | *psicología* | Consideraciones sobre Olaf, la conducta motivada, y la trazabilidad del pensamiento [33:43]
   💀 El suicidio del arquitecto en Prometheus y el significado de la sustancia negra
   - El arquitecto se suicida porque no puede soportar su propia obra: la creación de la sustancia negra que aísla el mal
- El significado del inicio de Prometheus se explica al final de Alien Covenant con la frase "Me he convertido en muerte,...

**5.** `0.3333` | *análisis de obra* | Un Gólem llamado Prometeo [59:32]
   🛸 La nave de destrucción masiva: los ingenieros planeaban exterminar a la humanidad con materia oscura
   - La estructura no era una instalación científica sino una nave cargada de sustancia negra con destino la Tierra como arma química
- El plan original fracasó porque la sustancia se volvió contra los propios ingenieros durante la misión y lo...

### Dense+Reranker top-5

**1.** `0.9204` | *análisis de obra* | Un Gólem llamado Prometeo [51:26]  **<- chunk fuente**
   🩸 La cirugía del feto alienígena: Elizabeth como madre involuntaria que extrae su horror
   - David informa a Elizabeth que tiene un "feto de 3 meses" dentro pese a haber tenido sexo solo 10 horas antes — y no es un feto normal
- En lugar de operarla, David sugiere mantenerla en hibernación; ella escapa y usa la cápsula médica de ...

**2.** `0.0891` | *análisis de obra* | Un Gólem llamado Prometeo. [21:12]
   🧬 La escena inicial de Prometheus: el ingeniero y la sustancia negra
   - Un ser proto-humano bebe una sustancia que destruye su ADN desde dentro y cae disuelto en una cascada
- De sus restos en el agua surge una nueva cadena parecida al ADN que genera células: el origen de la vida humana
- Primera polaridad ex...

**3.** `0.0426` | *análisis de obra* | Un Gólem llamado Prometeo [1:04:08]
   🔭 Elizabeth como síntesis de ciencia, fe y búsqueda humana de los orígenes
   - Último informe de Elizabeth: "Soy la última superviviente del Prometheus y continúo buscando"
- Representa simultáneamente la ciencia, la fe y la unión de ambas que constituye a la humanidad
- Antes de los créditos: su "hijo" cefalópodo +...

**4.** `0.0180` | *análisis de obra* | Un Gólem llamado Prometeo. [53:58]
   👽 La extracción del parásito y el descubrimiento de Weylandt
   - La protagonista se extrae un ser con forma marina-cefalópodo del tamaño de un feto de 18 semanas
- Weylandt viajaba oculto en la nave: su verdadero objetivo no era conocer sus orígenes sino obtener la inmortalidad
- La comandante es revel...

**5.** `0.0173` | *análisis de obra* | Un Gólem llamado Prometeo [47:53]
   🪱 La sustancia negra muta lombrices: el caos corrompe incluso la vida más simple
   - Dos científicos atrapados en la estructura observan cómo pequeñas lombrices del suelo se transforman al contacto con la sustancia negra en criaturas depredadoras letales
- El biólogo muere devorado; simultáneamente, Holloway (pareja de El...

---

## q05 -- *proper_noun* -- análisis de obra

> **qué es el Malleus Maleficarum y qué relevancia tiene en la persecución de brujas**

_Hipótesis: Término latino raro. Sparse debería ganar; dense puede traer chunks generales sobre brujería._

_Posición chunk fuente_: dense20=1 | dense5=1 | RRF5=1 | reranker5=1

### Dense top-5

**1.** `0.5517` | *análisis de obra* | Análisis arquetípico La Bruja [45:22]  **<- chunk fuente**
   📜 El Malleus Maleficarum y la personificación del mal
   - El tratado sobre brujería recopilaba ritos alejandrinos, paganos y leyenda popular, y tuvo bula papal
- Las brujas untaban palos con sustancias enteógenas que absorbidas por mucosas provocaban viajes alucinatorios — origen de "montar en e...

**2.** `0.4581` | *análisis de obra* | El Sueño Eterno: Análisis Arquetípico de la Bella Durmiente. [26:00]
   💚 La entrada de Maléfica: el mal antinatural y la envidia
   - El resplandor verde es completamente antinatural: verde y noche no cuadran, es fuego fatuo, es muerte
- Maléfica entra con un rayo en lugar de un haz de luz, una forma brusca y drástica frente a la entrada suave de las hadas
- Maléfica co...

**3.** `0.4204` | *análisis de obra* | Análisis: Nosferatu (Eggers, 2024). El último Mito Polar [25:14]
   😈 La peor víctima y el peor mal: el destino manifiesto de Nosferatu
   - Qué pasaría si el mal personificado tentara a una niña prematura sexualmente con instintos excesivamente fuertes
- La portada es un destino manifiesto: un hieros gamos invertido donde la bestia mira al vacío y ella nos mira a nosotros
- N...

**4.** `0.4142` | *mitología y religión* | Otoño de cuentos. Lovecraft [1:05:01]
   📕 El Necronomicón como eje de la mitología lovecraftiana
   - El Necronomicón es el libro que articula el centro de los relatos de terror de Lovecraft
- Los relatos con más lore común son el Necronomicón, La llamada de Cthulhu y En las montañas de la locura

**5.** `0.4066` | *análisis de obra* | Caperucita Roja: ¿A quién tienes miedo? [52:16]
   😈 El encuentro con el mal: ingenuo, encarnado o no personificado
   - El encuentro con el mal es inicialmente ingenuo: no se le reconoce o surge de donde no debería provenir
- El mal encarnado (dragón, lobo) produce terror porque tiene objeto; el mal no personificado (caos, desorden) produce angustia o mist...

### RRF top-5

**1.** `1.0000` | *análisis de obra* | Análisis arquetípico La Bruja [45:22]  **<- chunk fuente**
   📜 El Malleus Maleficarum y la personificación del mal
   - El tratado sobre brujería recopilaba ritos alejandrinos, paganos y leyenda popular, y tuvo bula papal
- Las brujas untaban palos con sustancias enteógenas que absorbidas por mucosas provocaban viajes alucinatorios — origen de "montar en e...

**2.** `0.5333` | *análisis de obra* | El Sueño Eterno: Análisis Arquetípico de la Bella Durmiente. [26:00]
   💚 La entrada de Maléfica: el mal antinatural y la envidia
   - El resplandor verde es completamente antinatural: verde y noche no cuadran, es fuego fatuo, es muerte
- Maléfica entra con un rayo en lugar de un haz de luz, una forma brusca y drástica frente a la entrada suave de las hadas
- Maléfica co...

**3.** `0.3611` | *mitología y religión* | Mitología 101: Perséfone [51:41]
   🧙‍♀️ Hécate: la bruja como rescatadora
   - Deméter llama a Hécate, aspecto divino que representa la parte oscura de la feminidad mágica, la luna del tarot
- Hécate es la rebeldía, el hartazgo, la salida voluntaria de la civilización, la búsqueda de secretos prohibidos por el patri...

**4.** `0.3333` | *psicología* | Vacacioff: De la Sartén a Venezuela (parte II) [1:39:39]
   🧹 La bruja real versus la estética de bruja
   - Una bruja no es quien practica brujería sino quien rechaza lo civilizatorio buscando fuerzas demoníacas naturales
- Las hécatas quieren ser brujas pero no lo son psicológicamente
- A las brujas reales no les atraen los emos; los emos atra...

**5.** `0.2500` | *análisis de obra* | Análisis: Nosferatu (Eggers, 2024). El último Mito Polar [25:14]
   😈 La peor víctima y el peor mal: el destino manifiesto de Nosferatu
   - Qué pasaría si el mal personificado tentara a una niña prematura sexualmente con instintos excesivamente fuertes
- La portada es un destino manifiesto: un hieros gamos invertido donde la bestia mira al vacío y ella nos mira a nosotros
- N...

### Dense+Reranker top-5

**1.** `0.8095` | *análisis de obra* | Análisis arquetípico La Bruja [45:22]  **<- chunk fuente**
   📜 El Malleus Maleficarum y la personificación del mal
   - El tratado sobre brujería recopilaba ritos alejandrinos, paganos y leyenda popular, y tuvo bula papal
- Las brujas untaban palos con sustancias enteógenas que absorbidas por mucosas provocaban viajes alucinatorios — origen de "montar en e...

**2.** `0.0031` | *análisis de obra* | El Sueño Eterno: Análisis Arquetípico de la Bella Durmiente. [26:00]
   💚 La entrada de Maléfica: el mal antinatural y la envidia
   - El resplandor verde es completamente antinatural: verde y noche no cuadran, es fuego fatuo, es muerte
- Maléfica entra con un rayo en lugar de un haz de luz, una forma brusca y drástica frente a la entrada suave de las hadas
- Maléfica co...

**3.** `0.0022` | *análisis de obra* | Suspiria: El Maligno y el Mito Lunar [1:47:10]
   👑 La revelación: Susi es la verdadera Mater Suspiriorum
   - Madre Marcos busca traspasar su cuerpo decrépito al cuerpo joven de Susi
- El ritual exige renegar de la madre anterior y vaciarse para ser receptáculo del mal
- Susi descubre su propio poder y declara "Yo soy ella": la verdadera Mater Su...

**4.** `0.0013` | *mitología y religión* | Mitología 101: Perséfone [51:41]
   🧙‍♀️ Hécate: la bruja como rescatadora
   - Deméter llama a Hécate, aspecto divino que representa la parte oscura de la feminidad mágica, la luna del tarot
- Hécate es la rebeldía, el hartazgo, la salida voluntaria de la civilización, la búsqueda de secretos prohibidos por el patri...

**5.** `0.0011` | *análisis de obra* | El Sueño Eterno: Análisis Arquetípico de la Bella Durmiente. [1:54:33]
   🔄 La interpretación invertida de Maléfica (2014)
   - La película Maléfica pone como protagonista a la envidia y propone que la solución es que la envidia perdone a la doncella
- Esto contradice la estructura original: el cuento dice que hay que salir a los salvajes y enfrentar el destino, n...

---

## q06 -- *paraphrase* -- análisis de obra

> **cómo consigue la película que el espectador se identifique emocionalmente con la culpa del personaje al haber hecho daño sin querer**

_Hipótesis: Paráfrasis sin nombrar Frozen ni Elsa. Estresa sparse, dense debería capturar el concepto._

_Posición chunk fuente_: dense20=1 | dense5=1 | RRF5=1 | reranker5=1

### Dense top-5

**1.** `0.5990` | *análisis de obra* | Análisis arquetípico Frozen [1:09:24]  **<- chunk fuente**
   🧊 El accidente y la semilla de culpa: Elsa como portadora de una maldición autoimpuesta
   - Jugando con el hielo Elsa hiere a Ana sin querer y algo completamente maravilloso se convierte en algo peligroso
- Cuanto peor se siente Elsa más frío lanza: su don hace daño a los demás y desde muy pequeña se siente culpable porque cree ...

**2.** `0.5678` | *análisis de obra* | Análisis arquetípico La Bruja [2:00:07]
   🪞 La historia paralela: una joven con experiencias sexuales prematuras
   - La película puede leerse como la historia de una mujer joven inconsciente de su atractivo que se deja llevar por sus instintos junto a un joven incapaz de lidiar con la culpa
- Mujeres con experiencias sexuales prematuras y rechazadas cre...

**3.** `0.5627` | *análisis de obra* | Análisis arquetípico La Bruja [1:36:57]
   🐑 El padre busca un chivo expiatorio para no reconocer su fracaso
   - El padre necesita que alguien confiese haber pactado con el mal porque personificar la culpa fuera le permite no cuestionar su propia fe
- Los mellizos caen en letargo incapaces de rezar; Taylor es la única indemne, lo que paradójicamente...

**4.** `0.5534` | *análisis de obra* | Análisis arquetípico Frozen [1:14:27]
   🪞 Frozen como espejo de la herida narcisista: identificación con la víctima incomprendida
   - Disney consigue que toda persona con una idea de infancia en la que fue el centro incomprendido de un conflicto se identifique mágicamente con Elsa
- El héroe nunca tiene poder ilimitado desde el principio; tiene que hacérselo merecer, pe...

**5.** `0.5520` | *psicología* | Lunes 100 tífiko: Therians [57:57]
   ⚔️ Convertir lo que haces en lo que eres fabrica villanos
   - Si conviertes algo ridículo que haces en "lo que eres", quien te critica se convierte automáticamente en villano
- Toda la dinámica es una película autoimpuesta: el terian como héroe incomprendido de anime
- La gente no humilla lo que ere...

### RRF top-5

**1.** `1.0000` | *análisis de obra* | Análisis arquetípico Frozen [1:09:24]  **<- chunk fuente**
   🧊 El accidente y la semilla de culpa: Elsa como portadora de una maldición autoimpuesta
   - Jugando con el hielo Elsa hiere a Ana sin querer y algo completamente maravilloso se convierte en algo peligroso
- Cuanto peor se siente Elsa más frío lanza: su don hace daño a los demás y desde muy pequeña se siente culpable porque cree ...

**2.** `0.4167` | *análisis de obra* | Análisis arquetípico La Bruja [2:00:07]
   🪞 La historia paralela: una joven con experiencias sexuales prematuras
   - La película puede leerse como la historia de una mujer joven inconsciente de su atractivo que se deja llevar por sus instintos junto a un joven incapaz de lidiar con la culpa
- Mujeres con experiencias sexuales prematuras y rechazadas cre...

**3.** `0.3333` | *cultura y actualidad* | Anonimato y minoría de edad en redes sociales. [29:34]
   ⚖️ Responsabilidad parental como alternativa real a la prohibición
   - Si tu hijo hace daño a otro a través de la red, la responsabilidad civil es tuya; debería ser obligatorio un seguro
- Si tu hijo se ve expuesto a contenido inadecuado y te pillan, multa y cárcel progresiva hasta la pérdida de custodia
- S...

**4.** `0.2500` | *análisis de obra* | Análisis arquetípico La Bruja [1:36:57]
   🐑 El padre busca un chivo expiatorio para no reconocer su fracaso
   - El padre necesita que alguien confiese haber pactado con el mal porque personificar la culpa fuera le permite no cuestionar su propia fe
- Los mellizos caen en letargo incapaces de rezar; Taylor es la única indemne, lo que paradójicamente...

**5.** `0.2500` | *análisis de obra* | Análisis arquetípico La Bruja [2:15:15]
   ⚡ Debate: ¿la religión crea la culpa o responde a ella?
   - La religión no crea la culpa; la culpa la sientes internamente y la religión es una respuesta a esa culpa interna
- Algunas doctrinas religiosas introducen la culpa como método articulatorio del deber ser, pero no es inherente a toda reli...

### Dense+Reranker top-5

**1.** `0.7003` | *análisis de obra* | Análisis arquetípico Frozen [1:09:24]  **<- chunk fuente**
   🧊 El accidente y la semilla de culpa: Elsa como portadora de una maldición autoimpuesta
   - Jugando con el hielo Elsa hiere a Ana sin querer y algo completamente maravilloso se convierte en algo peligroso
- Cuanto peor se siente Elsa más frío lanza: su don hace daño a los demás y desde muy pequeña se siente culpable porque cree ...

**2.** `0.0198` | *análisis de obra* | Análisis arquetípico Frozen [1:14:27]
   🪞 Frozen como espejo de la herida narcisista: identificación con la víctima incomprendida
   - Disney consigue que toda persona con una idea de infancia en la que fue el centro incomprendido de un conflicto se identifique mágicamente con Elsa
- El héroe nunca tiene poder ilimitado desde el principio; tiene que hacérselo merecer, pe...

**3.** `0.0129` | *análisis de obra* | Análisis arquetípico La Bruja [1:36:57]
   🐑 El padre busca un chivo expiatorio para no reconocer su fracaso
   - El padre necesita que alguien confiese haber pactado con el mal porque personificar la culpa fuera le permite no cuestionar su propia fe
- Los mellizos caen en letargo incapaces de rezar; Taylor es la única indemne, lo que paradójicamente...

**4.** `0.0126` | *análisis de obra* | Análisis arquetípico La Bruja [2:00:07]
   🪞 La historia paralela: una joven con experiencias sexuales prematuras
   - La película puede leerse como la historia de una mujer joven inconsciente de su atractivo que se deja llevar por sus instintos junto a un joven incapaz de lidiar con la culpa
- Mujeres con experiencias sexuales prematuras y rechazadas cre...

**5.** `0.0105` | *análisis de obra* | El Sueño Eterno: Análisis Arquetípico de la Bella Durmiente. [1:56:34]
   📖 El meta-cuento: la moraleja se cuenta a sí misma
   - La película se abre como un cuento porque el receptor debe sacar la moraleja, no simplemente recibir una historia
- Es un meta-cuento: la historia se está contando a sí misma como inevitable y al mismo tiempo como advertencia
- Toda la pe...

---

## q07 -- *proper_noun* -- cultura y actualidad

> **rumores de que Diddy ordenó la muerte de Tupac y Notorious BIG**

_Hipótesis: Nombres propios concretos. Sparse debería dominar._

_Posición chunk fuente_: dense20=1 | dense5=1 | RRF5=1 | reranker5=1

### Dense top-5

**1.** `0.7276` | *cultura y actualidad* | La Batalla Espiritual [37:25]  **<- chunk fuente**
   🎤 Diddy como productor musical y la rivalidad costa este-oeste
   - Diddy fundó el sello Bad Boy Records y prácticamente todo lo que tocaba se convertía en oro como productor
- Siempre se rumoreó que ordenó el asesinato de Tupac; poco después también murió tiroteado Notorious B.I.G.
- Se rumorea que Diddy...

**2.** `0.5441` | *cultura y actualidad* | La Batalla Espiritual [1:09:20]
   🏠 El túnel secreto, Sony Music y la muerte de Michael Jackson
   - Se rumoreó un túnel entre la casa de Diddy y la de Michael Jackson; es falso, pero abre el tema de Jackson
- Jackson estaba enfrentado a Sony Music y su jefe Tommy Mottola; se acusa a Mottola de los mismos abusos que a Diddy y de haber si...

**3.** `0.4864` | *cultura y actualidad* | La Batalla Espiritual [46:01]
   🎉 Las fiestas de Diddy: White Parties y Freak Out Parties
   - Las White Parties eran eventos de alto perfil donde asistían Leonardo DiCaprio, Ashton Kutcher, Trump, Michael Jackson — no eras nadie si no estabas invitado
- Las Freak Out Parties se hacían en suites de hotel sin móviles; había habitaci...

**4.** `0.4773` | *cultura y actualidad* | La Batalla Espiritual [1:28:03]
   ⚰️ Kim Porter: la primera mujer de Diddy
   - Murió en 2018 supuestamente de neumonía; su padre siempre ha dicho que Diddy se la cargó directa o indirectamente
- Salió un libro póstumo donde ella relataba maltrato, sexo forzado con terceros, drogas y grabaciones — el mismo patrón que...

**5.** `0.4760` | *cultura y actualidad* | La Batalla Espiritual [1:05:49]
   🎵 Britney Spears como posible víctima de Diddy
   - Las primeras veces que pillaron a Britney en escándalos salía de fiestas de Diddy; ella siempre dijo que le pusieron algo en la bebida
- En la gala MTV 2007 hay vídeos de ella perfectamente en ensayos y completamente ida después
- Se sugi...

### RRF top-5

**1.** `1.0000` | *cultura y actualidad* | La Batalla Espiritual [37:25]  **<- chunk fuente**
   🎤 Diddy como productor musical y la rivalidad costa este-oeste
   - Diddy fundó el sello Bad Boy Records y prácticamente todo lo que tocaba se convertía en oro como productor
- Siempre se rumoreó que ordenó el asesinato de Tupac; poco después también murió tiroteado Notorious B.I.G.
- Se rumorea que Diddy...

**2.** `0.6667` | *cultura y actualidad* | La Batalla Espiritual [1:09:20]
   🏠 El túnel secreto, Sony Music y la muerte de Michael Jackson
   - Se rumoreó un túnel entre la casa de Diddy y la de Michael Jackson; es falso, pero abre el tema de Jackson
- Jackson estaba enfrentado a Sony Music y su jefe Tommy Mottola; se acusa a Mottola de los mismos abusos que a Diddy y de haber si...

**3.** `0.4500` | *cultura y actualidad* | La Batalla Espiritual [46:01]
   🎉 Las fiestas de Diddy: White Parties y Freak Out Parties
   - Las White Parties eran eventos de alto perfil donde asistían Leonardo DiCaprio, Ashton Kutcher, Trump, Michael Jackson — no eras nadie si no estabas invitado
- Las Freak Out Parties se hacían en suites de hotel sin móviles; había habitaci...

**4.** `0.3409` | *cultura y actualidad* | La Batalla Espiritual [27:49]
   🔍 Caso P. Diddy: los hechos formales y acusaciones
   - Una exnovia (Cassie Ventura) le denunció en 2023 por maltrato hardcore, existe vídeo de cámaras de seguridad pegándola en un hotel
- Se le acusa de obligar a parejas a tomar drogas, mantener relaciones con terceros estando drogadas, y gra...

**5.** `0.3000` | *cultura y actualidad* | La Batalla Espiritual [1:28:03]
   ⚰️ Kim Porter: la primera mujer de Diddy
   - Murió en 2018 supuestamente de neumonía; su padre siempre ha dicho que Diddy se la cargó directa o indirectamente
- Salió un libro póstumo donde ella relataba maltrato, sexo forzado con terceros, drogas y grabaciones — el mismo patrón que...

### Dense+Reranker top-5

**1.** `0.9946` | *cultura y actualidad* | La Batalla Espiritual [37:25]  **<- chunk fuente**
   🎤 Diddy como productor musical y la rivalidad costa este-oeste
   - Diddy fundó el sello Bad Boy Records y prácticamente todo lo que tocaba se convertía en oro como productor
- Siempre se rumoreó que ordenó el asesinato de Tupac; poco después también murió tiroteado Notorious B.I.G.
- Se rumorea que Diddy...

**2.** `0.0630` | *cultura y actualidad* | La Batalla Espiritual [1:09:20]
   🏠 El túnel secreto, Sony Music y la muerte de Michael Jackson
   - Se rumoreó un túnel entre la casa de Diddy y la de Michael Jackson; es falso, pero abre el tema de Jackson
- Jackson estaba enfrentado a Sony Music y su jefe Tommy Mottola; se acusa a Mottola de los mismos abusos que a Diddy y de haber si...

**3.** `0.0126` | *cultura y actualidad* | La Batalla Espiritual [42:28]
   🔫 El tiroteo en la fiesta de Shine y la relación con Jennifer López
   - En una fiesta de presentación del disco de Shine (producido por Diddy) hubo un tiroteo dentro de la discoteca
- Shine cargó con toda la culpa y pasó 8 años en cárcel; después declaró que el arma era de Diddy
- Se rumorea que el FBI habría...

**4.** `0.0064` | *cultura y actualidad* | La Batalla Espiritual [1:29:35]
   😢 Justin Bieber como víctima del sistema
   - Usher, que vivió con Diddy desde los 13 años bajo custodia legal, produjo el primer single de Bieber ("Baby")
- Diddy buscó la custodia de Bieber (los padres no se la dieron) y pasaba mucho tiempo con él; existen vídeos incómodos de Diddy...

**5.** `0.0036` | *cultura y actualidad* | La Batalla Espiritual [1:05:49]
   🎵 Britney Spears como posible víctima de Diddy
   - Las primeras veces que pillaron a Britney en escándalos salía de fiestas de Diddy; ella siempre dijo que le pusieron algo en la bebida
- En la gala MTV 2007 hay vídeos de ella perfectamente en ensayos y completamente ida después
- Se sugi...

---

## q08 -- *natural* -- cultura y actualidad

> **¿por qué protestar en Ferraz tiene más sentido político que protestar frente al Congreso?**

_Hipótesis: Pregunta natural con términos del chunk (Ferraz, Congreso). Baseline._

_Posición chunk fuente_: dense20=1 | dense5=1 | RRF5=1 | reranker5=1

### Dense top-5

**1.** `0.7352` | *cultura y actualidad* | El país del fin del Mundo II. DANA. [15:47]  **<- chunk fuente**
   🏛️ Por qué protestar en Ferraz y no en el Congreso
   - Protestar frente al Congreso diluye la protesta porque es un edificio vacío que no representa a nadie concreto
- La izquierda lleva décadas monopolizando la lucha contra el sistema; ir al Congreso les regala legitimidad moral
- Protestar ...

**2.** `0.4879` | *cultura y actualidad* | Perro no come Perro [12:45]
   🔥 Estrategia revolucionaria para 2027: jornadas constituyentes
   - En 2027 España estará en crisis total, lo que permitirá tener a la izquierda callejera contra el PP
- Mientras la izquierda protesta contra el PP, el resto protesta contra Ferraz para derrocar el bipartidismo
- Se propone una nueva Consti...

**3.** `0.4480` | *cultura y actualidad* | El país del fin del Mundo II. DANA. [28:23]
   👑 La actuación del rey frente a la del gobierno en Paiporta
   - El rey mostró temple, gallardía y valor al exponerse sin escolta real entre la multitud enfurecida
- Representaba al Estado español, no a la casa Borbón como familia
- Sánchez estuvo "Sánchez" y Mazón se escondió detrás: contraste entre d...

**4.** `0.4448` | *cultura y actualidad* | El acabóse [1:43:57]
   🎭 Podemos Zaragoza como club de pijos con problemas con papá
   - Podemos Zaragoza era fundamentalmente gente privilegiada que se arrogaba la potestad de decir a los pobres qué les convenía
- Los ocupas actuales tienen cero riesgo real y se creen rebeldes al sistema
- Los jóvenes actuales del Frente Obr...

**5.** `0.4350` | *cultura y actualidad* | La PSOE lo ha conseguido, ESTO ES PEDRO SÁNCHEZ [1:41:21]
   🛡️ La Guardia Civil como único poder fáctico que lucha contra el gobierno
   - La Guardia Civil es el único poder fáctico que está luchando contra los excesos del gobierno
- Lo hacen porque tienen fuerza, poder y armas
- La independencia proviene de tener una esfera que los demás respetan porque tienes fuerza

### RRF top-5

**1.** `1.0000` | *cultura y actualidad* | El país del fin del Mundo II. DANA. [15:47]  **<- chunk fuente**
   🏛️ Por qué protestar en Ferraz y no en el Congreso
   - Protestar frente al Congreso diluye la protesta porque es un edificio vacío que no representa a nadie concreto
- La izquierda lleva décadas monopolizando la lucha contra el sistema; ir al Congreso les regala legitimidad moral
- Protestar ...

**2.** `0.6667` | *cultura y actualidad* | Perro no come Perro [12:45]
   🔥 Estrategia revolucionaria para 2027: jornadas constituyentes
   - En 2027 España estará en crisis total, lo que permitirá tener a la izquierda callejera contra el PP
- Mientras la izquierda protesta contra el PP, el resto protesta contra Ferraz para derrocar el bipartidismo
- Se propone una nueva Consti...

**3.** `0.2500` | *cultura y actualidad* | El país del fin del Mundo II. DANA. [28:23]
   👑 La actuación del rey frente a la del gobierno en Paiporta
   - El rey mostró temple, gallardía y valor al exponerse sin escolta real entre la multitud enfurecida
- Representaba al Estado español, no a la casa Borbón como familia
- Sánchez estuvo "Sánchez" y Mazón se escondió detrás: contraste entre d...

**4.** `0.2500` | *psicología* | Psicología 101: Cómo un Pollo demostró a Jung [39:58]
   🔀 Multimodalidad frente a sinestesia
   - La sinestesia es percibir un sentido como si fuera otro (cruce de sentidos), mientras que la multimodalidad es activar diferentes partes del cerebro simultáneamente
- El efecto Buba-Kiki no es sinestesia sino asociación multimodal
- Sines...

**5.** `0.2000` | *cultura y actualidad* | El acabóse [1:43:57]
   🎭 Podemos Zaragoza como club de pijos con problemas con papá
   - Podemos Zaragoza era fundamentalmente gente privilegiada que se arrogaba la potestad de decir a los pobres qué les convenía
- Los ocupas actuales tienen cero riesgo real y se creen rebeldes al sistema
- Los jóvenes actuales del Frente Obr...

### Dense+Reranker top-5

**1.** `0.9990` | *cultura y actualidad* | El país del fin del Mundo II. DANA. [15:47]  **<- chunk fuente**
   🏛️ Por qué protestar en Ferraz y no en el Congreso
   - Protestar frente al Congreso diluye la protesta porque es un edificio vacío que no representa a nadie concreto
- La izquierda lleva décadas monopolizando la lucha contra el sistema; ir al Congreso les regala legitimidad moral
- Protestar ...

**2.** `0.0542` | *cultura y actualidad* | Perro no come Perro [12:45]
   🔥 Estrategia revolucionaria para 2027: jornadas constituyentes
   - En 2027 España estará en crisis total, lo que permitirá tener a la izquierda callejera contra el PP
- Mientras la izquierda protesta contra el PP, el resto protesta contra Ferraz para derrocar el bipartidismo
- Se propone una nueva Consti...

**3.** `0.0062` | *cultura y actualidad* | He visto a Paloma [15:13]
   🗣️ Infoblogger y la crítica al bipartidismo PP-PSOE
   - Infoblogger argumenta que estar frente a Moncloa es lo más cerca que pueden estar de que Sánchez les escuche
- Critica al PP por convocar su manifestación dos semanas después en lugar de acudir a la convocatoria espontánea
- Acusa al PP d...

**4.** `0.0001` | *cultura y actualidad* | Proxy T4, 4x01: "Piloto" [43:15]
   🧠 Cámaras de eco y adherencia ideológica como fenómeno psicológico
   - La gente apoya ideas porque les facilitan la catarsis o la manifestación de su neurosis
- La posición política es adherencia: nos agregamos a grupos cuya estructura dialéctica encaja con nuestra personalidad
- Los insultos recibidos de se...

**5.** `0.0001` | *cultura y actualidad* | Se celebrarán juicios [33:40]
   💢 Del deseo de justicia al deseo de venganza ciudadana
   - El ciudadano está pasando de querer justicia a querer venganza como consecuencia de la mala política acumulada
- El problema político no es la mala gestión sino la corrupción moral activa y deliberada
- España es "opaca": no se puede sabe...

---

## q09 -- *paraphrase* -- filosofía y teoría

> **diferencia entre lo que se anhela activamente y lo que se sabe imposible y se disfruta como ficción**

_Hipótesis: Paráfrasis abstracta de fantasía vs anhelo. Dense debería capturar el concepto._

_Posición chunk fuente_: dense20=1 | dense5=1 | RRF5=1 | reranker5=1

### Dense top-5

**1.** `0.6221` | *filosofía y teoría* | Inteligencia Real e Inteligencia Artificial [1:00:05]  **<- chunk fuente**
   🌀 Fantasía, anhelo y futuro como categorías afectivas
   - La fantasía es una ficción que sabemos imposible y en la que nos quedamos sin forzar que ocurra
- El cambio a la adultez es saber que no es posible alcanzar cierta ficción y llamarla fantasía
- El futuro deseable es aquel que voy a intent...

**2.** `0.5752` | *filosofía y teoría* | La teoría de la teoría de la mente [1:25:06]
   🎮 Fantasía vs. ficción: la función juego
   - La fantasía es una ficción que se sabe falsa, por tanto es recreativa y pertenece a la función juego
- La ficción puede ser una fantasía confabulada que se ha asumido como real, con consecuencias afectivas de realidad (ejemplo: un psicóti...

**3.** `0.5746` | *análisis de obra* | Harry Potter, el síndrome de Wendy y por qué es escoria fántastica [10:12]
   ⚔️ Drama vital frente a drama fantástico
   - El yo se identifica con procesos internos reales; el ello se identifica con procesos imaginarios
- Identificarse con Harry Potter es luchar contra el mal de los piratas de Peter Pan: inexistente en la vida real y por tanto fácil de vencer...

**4.** `0.5688` | *psicología* | Psicoanálisis de la orientación política: Dime a quién votas y te diré quién es tu madre. [19:14]
   💔 Anhelos, carencias y heridas fundamentales
   - Un anhelo es un deseo que depende de las carencias: se anhela aquello que no se tiene
- Las cosas tienen más importancia cuando no se poseen que cuando sí, porque la importancia es significado afectivo
- Las heridas fundamentales pueden s...

**5.** `0.5664` | *análisis de obra* | Sacrilegia (I). Aproximación arquetípica al tema en Bloodborne [00:00]
   🎭 La ficción como experiencia vivida
   - Toda historia de ficción consta de elementos esenciales que crean una representación en nuestra conciencia
- Las historias nos hacen vivir mentalmente lo que nos cuentan: no solo vemos una película, sino que la vivimos por dentro
- Las me...

### RRF top-5

**1.** `1.0000` | *filosofía y teoría* | Inteligencia Real e Inteligencia Artificial [1:00:05]  **<- chunk fuente**
   🌀 Fantasía, anhelo y futuro como categorías afectivas
   - La fantasía es una ficción que sabemos imposible y en la que nos quedamos sin forzar que ocurra
- El cambio a la adultez es saber que no es posible alcanzar cierta ficción y llamarla fantasía
- El futuro deseable es aquel que voy a intent...

**2.** `0.5333` | *psicología* | Psicoanálisis de la orientación política: Dime a quién votas y te diré quién es tu madre. [19:14]
   💔 Anhelos, carencias y heridas fundamentales
   - Un anhelo es un deseo que depende de las carencias: se anhela aquello que no se tiene
- Las cosas tienen más importancia cuando no se poseen que cuando sí, porque la importancia es significado afectivo
- Las heridas fundamentales pueden s...

**3.** `0.4444` | *filosofía y teoría* | La teoría de la teoría de la mente [1:25:06]
   🎮 Fantasía vs. ficción: la función juego
   - La fantasía es una ficción que se sabe falsa, por tanto es recreativa y pertenece a la función juego
- La ficción puede ser una fantasía confabulada que se ha asumido como real, con consecuencias afectivas de realidad (ejemplo: un psicóti...

**4.** `0.3111` | *mitología y religión* | El mito del Gólem: Transhumanismo [25:29]
   🚀 Ciencia ficción como la mejor fantasía posible
   - La mejor fantasía es la que más verdad contiene pareciendo lo contrario
- La diferencia entre ciencia ficción y cuento de hadas reside en el presupuesto de plausibilidad: técnica versus magia
- Alien es la forma más original de hablar de ...

**5.** `0.3095` | *análisis de obra* | Sacrilegia (I). Aproximación arquetípica al tema en Bloodborne [00:00]
   🎭 La ficción como experiencia vivida
   - Toda historia de ficción consta de elementos esenciales que crean una representación en nuestra conciencia
- Las historias nos hacen vivir mentalmente lo que nos cuentan: no solo vemos una película, sino que la vivimos por dentro
- Las me...

### Dense+Reranker top-5

**1.** `0.8159` | *filosofía y teoría* | Inteligencia Real e Inteligencia Artificial [1:00:05]  **<- chunk fuente**
   🌀 Fantasía, anhelo y futuro como categorías afectivas
   - La fantasía es una ficción que sabemos imposible y en la que nos quedamos sin forzar que ocurra
- El cambio a la adultez es saber que no es posible alcanzar cierta ficción y llamarla fantasía
- El futuro deseable es aquel que voy a intent...

**2.** `0.0701` | *psicología* | Psicoanálisis de la orientación política: Dime a quién votas y te diré quién es tu madre. [19:14]
   💔 Anhelos, carencias y heridas fundamentales
   - Un anhelo es un deseo que depende de las carencias: se anhela aquello que no se tiene
- Las cosas tienen más importancia cuando no se poseen que cuando sí, porque la importancia es significado afectivo
- Las heridas fundamentales pueden s...

**3.** `0.0330` | *filosofía y teoría* | La teoría de la teoría de la mente [1:25:06]
   🎮 Fantasía vs. ficción: la función juego
   - La fantasía es una ficción que se sabe falsa, por tanto es recreativa y pertenece a la función juego
- La ficción puede ser una fantasía confabulada que se ha asumido como real, con consecuencias afectivas de realidad (ejemplo: un psicóti...

**4.** `0.0199` | *análisis de obra* | Enredados: Análisis de la madre oscura en Disney. [24:11]
   🪟 La intuición de la diosa: imaginar lo que existe sin haberlo visto
   - Lo femenino tiene la capacidad de imaginar cosas nunca vistas que pertenecen al mundo: los arquetipos
- Rapunzel mira por la ventana y anhela comprender qué hay más allá; su intuición le dice que la vida es más que estar encerrada
- El an...

**5.** `0.0121` | *análisis de obra* | Sacrilegia (I). Aproximación arquetípica al tema en Bloodborne [00:00]
   🎭 La ficción como experiencia vivida
   - Toda historia de ficción consta de elementos esenciales que crean una representación en nuestra conciencia
- Las historias nos hacen vivir mentalmente lo que nos cuentan: no solo vemos una película, sino que la vivimos por dentro
- Las me...

---

## q10 -- *proper_noun* -- mitología y religión

> **qué cambio experimenta Manwë en su visión gracias al pensamiento de Yavana**

_Hipótesis: Nombres propios raros del Silmarillion. Sparse muy fuerte aquí._

_Posición chunk fuente_: dense20=1 | dense5=1 | RRF5=1 | reranker5=1

### Dense top-5

**1.** `0.6706` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [32:29]  **<- chunk fuente**
   🌟 La iluminación femenina transforma la visión de Manwë
   - El pensamiento de Yavana puesto en el corazón de Manwë crece hasta que Ilúvatar lo ve
- La visión de Manwë se renueva y ya no es remota: él mismo está dentro de ella, como una nueva comprensión
- La diosa blanca entrega una espada a lo ma...

**2.** `0.6592` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [32:29]
   💡 La iluminación femenina renueva la visión de Manwë
   - El pensamiento de Yavanna puesto en el corazón de Manwë crece hasta que Ilúvatar lo ve
- La visión se renueva: ya no es remota, ahora Manwë es protagonista dentro de ella
- La diosa blanca le da una espada a lo masculino: posibilidad de j...

**3.** `0.5902` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [27:26]
   🔮 La introspección de Yavana ante Manwë: el anhelo femenino
   - Yavana acude a Manwë angustiada por lo que pueda hacerse en la Tierra Media en los días por venir
- Yavana contempla sus propios pensamientos: la introspección femenina como componente del golem
- Desea que los árboles pudieran hablar y c...

**4.** `0.5885` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [27:57]
   🪞 La introspección femenina: la diosa contempla sus propios pensamientos
   - Yavanna cayó y contempló sus propios pensamientos: esa es la introspección de lo femenino
- La conciencia femenina reconoce un anhelo implícito que no puede determinar pero que está ahí
- Yavanna acude a Manwë buscando esperanza, como jov...

**5.** `0.5545` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [40:08]
   🦅 Las Águilas y la separación entre gloria explícita y magia arcana
   - Manwë dice que el pensamiento de Yavana y el suyo remontaron vuelo juntos como grandes aves — unión de tierra y aire
- Yavana desea que sus árboles crezcan tan alto como el intelecto, pero Manwë limita: solo las montañas alcanzarán esa gl...

### RRF top-5

**1.** `1.0000` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [32:29]  **<- chunk fuente**
   🌟 La iluminación femenina transforma la visión de Manwë
   - El pensamiento de Yavana puesto en el corazón de Manwë crece hasta que Ilúvatar lo ve
- La visión de Manwë se renueva y ya no es remota: él mismo está dentro de ella, como una nueva comprensión
- La diosa blanca entrega una espada a lo ma...

**2.** `0.5833` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [27:26]
   🔮 La introspección de Yavana ante Manwë: el anhelo femenino
   - Yavana acude a Manwë angustiada por lo que pueda hacerse en la Tierra Media en los días por venir
- Yavana contempla sus propios pensamientos: la introspección femenina como componente del golem
- Desea que los árboles pudieran hablar y c...

**3.** `0.5333` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [32:29]
   💡 La iluminación femenina renueva la visión de Manwë
   - El pensamiento de Yavanna puesto en el corazón de Manwë crece hasta que Ilúvatar lo ve
- La visión se renueva: ya no es remota, ahora Manwë es protagonista dentro de ella
- La diosa blanca le da una espada a lo masculino: posibilidad de j...

**4.** `0.4167` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [40:08]
   🦅 Las Águilas y la separación entre gloria explícita y magia arcana
   - Manwë dice que el pensamiento de Yavana y el suyo remontaron vuelo juntos como grandes aves — unión de tierra y aire
- Yavana desea que sus árboles crezcan tan alto como el intelecto, pero Manwë limita: solo las montañas alcanzarán esa gl...

**5.** `0.3250` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [27:57]
   🪞 La introspección femenina: la diosa contempla sus propios pensamientos
   - Yavanna cayó y contempló sus propios pensamientos: esa es la introspección de lo femenino
- La conciencia femenina reconoce un anhelo implícito que no puede determinar pero que está ahí
- Yavanna acude a Manwë buscando esperanza, como jov...

### Dense+Reranker top-5

**1.** `0.9885` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [32:29]  **<- chunk fuente**
   🌟 La iluminación femenina transforma la visión de Manwë
   - El pensamiento de Yavana puesto en el corazón de Manwë crece hasta que Ilúvatar lo ve
- La visión de Manwë se renueva y ya no es remota: él mismo está dentro de ella, como una nueva comprensión
- La diosa blanca entrega una espada a lo ma...

**2.** `0.9741` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [32:29]
   💡 La iluminación femenina renueva la visión de Manwë
   - El pensamiento de Yavanna puesto en el corazón de Manwë crece hasta que Ilúvatar lo ve
- La visión se renueva: ya no es remota, ahora Manwë es protagonista dentro de ella
- La diosa blanca le da una espada a lo masculino: posibilidad de j...

**3.** `0.7938` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [40:08]
   🦅 Las Águilas y la separación entre gloria explícita y magia arcana
   - Manwë dice que el pensamiento de Yavana y el suyo remontaron vuelo juntos como grandes aves — unión de tierra y aire
- Yavana desea que sus árboles crezcan tan alto como el intelecto, pero Manwë limita: solo las montañas alcanzarán esa gl...

**4.** `0.7324` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [27:26]
   🔮 La introspección de Yavana ante Manwë: el anhelo femenino
   - Yavana acude a Manwë angustiada por lo que pueda hacerse en la Tierra Media en los días por venir
- Yavana contempla sus propios pensamientos: la introspección femenina como componente del golem
- Desea que los árboles pudieran hablar y c...

**5.** `0.6032` | *mitología y religión* | ¡Inside Proxy está emitiendo en directo! [27:57]
   🪞 La introspección femenina: la diosa contempla sus propios pensamientos
   - Yavanna cayó y contempló sus propios pensamientos: esa es la introspección de lo femenino
- La conciencia femenina reconoce un anhelo implícito que no puede determinar pero que está ahí
- Yavanna acude a Manwë buscando esperanza, como jov...

---

## q11 -- *adversarial_colloquial* -- análisis de obra

> **esa peli del alien donde la tía se opera ella misma para sacarse el bicho**

_Hipótesis: Coloquial extremo + sin nombres propios (Prometheus/Elizabeth/cápsula). Estresa dense al máximo._

_Posición chunk fuente_: dense20=1 | dense5=1 | RRF5=2 | reranker5=1

### Dense top-5

**1.** `0.5302` | *análisis de obra* | Un Gólem llamado Prometeo [51:26]  **<- chunk fuente**
   🩸 La cirugía del feto alienígena: Elizabeth como madre involuntaria que extrae su horror
   - David informa a Elizabeth que tiene un "feto de 3 meses" dentro pese a haber tenido sexo solo 10 horas antes — y no es un feto normal
- En lugar de operarla, David sugiere mantenerla en hibernación; ella escapa y usa la cápsula médica de ...

**2.** `0.5046` | *análisis de obra* | Mitología 101: Alien y el mito Polar. (NO spoliers de Alien Romulus) [55:37]
   🚀 Estructura idéntica del final de todas las películas de Alien
   - Todas acaban con el último encuentro de la diosa con el mal y la expulsión del mal de la nave nodriza
- Existe siempre: una gran madre (naturaleza), una hija (diosa-protagonista), una corporación (naturaleza artificial), un gólem (hijo de...

**3.** `0.4850` | *análisis de obra* | Un Gólem llamado Prometeo [1:34:41]
   🕷️ La Madre Oscura: Ripley como la madre infértil que destruye su propia creación
   - El arquetipo de la madre oscura: la madre que engendra seres para devorarlos o destruirlos
- Ripley en todas las películas es la madre infértil heredera de la luminosidad (linaje de Elizabeth) con una parte oscura: destruir al xenomorfo, ...

**4.** `0.4836` | *análisis de obra* | Mitología 101: Alien y el mito Polar. (NO spoliers de Alien Romulus) [52:36]
   👩 La diosa como salvadora frente al mal en todas las películas de Alien
   - En un contexto decadente donde la corporación (versión masculina que imita lo femenino) lleva a la humanidad a la decadencia
- Una mujer (la diosa, no un héroe) se ve envuelta sin llamada a la aventura en una lucha contra el mal en las pr...

**5.** `0.4728` | *análisis de obra* | Un Gólem llamado Prometeo. [39:56]
   🤖 El androide como primer golem de la película
   - El androide salva la vida de la protagonista mujer, patrón que se repite en todas las películas de Alien
- El androide se comunica en secreto con alguien llamándole "señor": existe un plan oculto por debajo de la misión científica
- La co...

### RRF top-5

**1.** `0.6250` | *análisis de obra* | Mitología 101: Alien y el mito Polar. (NO spoliers de Alien Romulus) [58:46]
   🧬 La evolución del Alien como integración con inteligencia máquina
   - El primer alien que existe es 100% biológico, pero a partir de ahí se mezcla con inteligencia máquina
- Los aliens pasan de seres salvajes a constructores con jerarquías complejísimas como las de Alien 3 con su reina
- El Alien evoluciona...

**2.** `0.5000` | *análisis de obra* | Un Gólem llamado Prometeo [51:26]  **<- chunk fuente**
   🩸 La cirugía del feto alienígena: Elizabeth como madre involuntaria que extrae su horror
   - David informa a Elizabeth que tiene un "feto de 3 meses" dentro pese a haber tenido sexo solo 10 horas antes — y no es un feto normal
- En lugar de operarla, David sugiere mantenerla en hibernación; ella escapa y usa la cápsula médica de ...

**3.** `0.4333` | *análisis de obra* | Mitología 101: Alien y el mito Polar. (NO spoliers de Alien Romulus) [55:37]
   🚀 Estructura idéntica del final de todas las películas de Alien
   - Todas acaban con el último encuentro de la diosa con el mal y la expulsión del mal de la nave nodriza
- Existe siempre: una gran madre (naturaleza), una hija (diosa-protagonista), una corporación (naturaleza artificial), un gólem (hijo de...

**4.** `0.3889` | *psicología* | Consideraciones sobre Olaf, la conducta motivada, y la trazabilidad del pensamiento [29:33]
   🧬 La genealogía del mal en Alien: de Prometheus a Alien Earth
   - En cada película el alien incorpora características humanas y los humanos incorporan características del mal
- La diosa (lo femenino eterno a través de Ripley) es la única que permanece haciendo equilibrios entre ambas líneas genealógicas...

**5.** `0.3088` | *psicología* | Consideraciones sobre Olaf, la conducta motivada, y la trazabilidad del pensamiento [26:32]
   👽 La estructura mitológica de la saga Alien y Alien Earth
   - Las series diluyen la estereotipia arquetípica al alargar la historia con relleno narrativo
- En Alien existe una triangulación entre la madre oscura (Weyland-Yutani), la diosa (Ripley) y el golem (el androide)
- El alien es una mezcla os...

### Dense+Reranker top-5

**1.** `0.0355` | *análisis de obra* | Un Gólem llamado Prometeo [51:26]  **<- chunk fuente**
   🩸 La cirugía del feto alienígena: Elizabeth como madre involuntaria que extrae su horror
   - David informa a Elizabeth que tiene un "feto de 3 meses" dentro pese a haber tenido sexo solo 10 horas antes — y no es un feto normal
- En lugar de operarla, David sugiere mantenerla en hibernación; ella escapa y usa la cápsula médica de ...

**2.** `0.0115` | *análisis de obra* | Mitología 101: Alien y el mito Polar. (NO spoliers de Alien Romulus) [55:37]
   🚀 Estructura idéntica del final de todas las películas de Alien
   - Todas acaban con el último encuentro de la diosa con el mal y la expulsión del mal de la nave nodriza
- Existe siempre: una gran madre (naturaleza), una hija (diosa-protagonista), una corporación (naturaleza artificial), un gólem (hijo de...

**3.** `0.0108` | *análisis de obra* | Mitología 101: Alien y el mito Polar. (NO spoliers de Alien Romulus) [52:36]
   👩 La diosa como salvadora frente al mal en todas las películas de Alien
   - En un contexto decadente donde la corporación (versión masculina que imita lo femenino) lleva a la humanidad a la decadencia
- Una mujer (la diosa, no un héroe) se ve envuelta sin llamada a la aventura en una lucha contra el mal en las pr...

**4.** `0.0086` | *análisis de obra* | Un Gólem llamado Prometeo. [39:56]
   🤖 El androide como primer golem de la película
   - El androide salva la vida de la protagonista mujer, patrón que se repite en todas las películas de Alien
- El androide se comunica en secreto con alguien llamándole "señor": existe un plan oculto por debajo de la misión científica
- La co...

**5.** `0.0075` | *análisis de obra* | Un Gólem llamado Prometeo [1:34:41]
   🕷️ La Madre Oscura: Ripley como la madre infértil que destruye su propia creación
   - El arquetipo de la madre oscura: la madre que engendra seres para devorarlos o destruirlos
- Ripley en todas las películas es la madre infértil heredera de la luminosidad (linaje de Elizabeth) con una parte oscura: destruir al xenomorfo, ...

---

## q12 -- *adversarial_paraphrase* -- análisis de obra

> **ese libro de brujas con bula del papa que justificaba la caza**

_Hipótesis: Paráfrasis lejana de Malleus Maleficarum sin usar el latín. Sin reranker, dense puede traer chunks generales sobre brujería._

_Posición chunk fuente_: dense20=1 | dense5=1 | RRF5=1 | reranker5=1

### Dense top-5

**1.** `0.5560` | *análisis de obra* | Análisis arquetípico La Bruja [45:22]  **<- chunk fuente**
   📜 El Malleus Maleficarum y la personificación del mal
   - El tratado sobre brujería recopilaba ritos alejandrinos, paganos y leyenda popular, y tuvo bula papal
- Las brujas untaban palos con sustancias enteógenas que absorbidas por mucosas provocaban viajes alucinatorios — origen de "montar en e...

**2.** `0.4893` | *análisis de obra* | Análisis arquetípico La Bruja [1:55:35]
   📖 El pacto con el diablo: la firma del libro y el vuelo
   - El diablo la tienta con cosas que no pertenecen al mundo del trabajo ni de lo real — la mujer intercambia lo civilizatorio por lo absolutamente ideal
- Ella no sabe escribir su nombre; el diablo dice "yo guiaré tu mano" — para pecar no ne...

**3.** `0.4822` | *mitología y religión* | Orfeo y Eurídice [44:03]
   🐍 La muerte de Eurídice: lo salvaje como peligro sin aviso
   - Eurídice huía de un pastor fauno que la quería raptar, representante de lo pueblerino y rústico
- Es mordida por una serpiente: símbolo de cómo lo salvaje es peligroso sin aviso, sin motivo y sin razón
- La muerte de Eurídice no tiene mor...

**4.** `0.4801` | *mitología y religión* | Eva, Lucifer, Satanás y la Serpiente. [1:12:16]
   ✝️ La Biblia no es una crónica de la lucha entre el bien y el mal
   - La Biblia es una crónica de la acción divina y la relación del hombre con Dios, no una pugna entre dos fuerzas
- Asimilar hechos naturales a causas sobrenaturales (espíritus del mal en objetos) es un error teológico propio del protestanti...

**5.** `0.4688` | *análisis de obra* | Suspiria: El Maligno y el Mito Lunar [1:06:48]
   🕸️ La vuelta a lo salvaje: la bruja como salida de lo civilizatorio
   - La bruja sale de la ciudad al bosque como vuelta voluntaria a lo salvaje por rechazo a la civilización
- Lo salvaje siempre albergará más mal que la civilización en sentido arquetípico
- La reutilización de los arcanos es salvajismo propi...

### RRF top-5

**1.** `0.7000` | *análisis de obra* | Análisis arquetípico La Bruja [45:22]  **<- chunk fuente**
   📜 El Malleus Maleficarum y la personificación del mal
   - El tratado sobre brujería recopilaba ritos alejandrinos, paganos y leyenda popular, y tuvo bula papal
- Las brujas untaban palos con sustancias enteógenas que absorbidas por mucosas provocaban viajes alucinatorios — origen de "montar en e...

**2.** `0.5000` | *análisis de obra* | Análisis arquetípico La Bruja [1:55:35]
   📖 El pacto con el diablo: la firma del libro y el vuelo
   - El diablo la tienta con cosas que no pertenecen al mundo del trabajo ni de lo real — la mujer intercambia lo civilizatorio por lo absolutamente ideal
- Ella no sabe escribir su nombre; el diablo dice "yo guiaré tu mano" — para pecar no ne...

**3.** `0.5000` | *análisis de obra* | Análisis arquetípico de Drácula, de Bram Stoker [41:11]
   ✝️ La cruz entre la bruma: civilización cristiana frente a la barbarie
   - La bruma simboliza aquello que oculta la mirada de quien se aventura en lo desconocido
- La cruz que sobresale representa la cristiandad como civilización
- La cruz cae y se rompe simbolizando el derrumbamiento del imperio cristiano en Or...

**4.** `0.3333` | *cultura y actualidad* | Vacacioff: De la Sartén a Venezuela. [19:55]
   🎭 Aclaración sobre rumores de "tirar la caña" en Twitter
   - La necesidad de justificarse ante rumores proviene de un trauma de humillación (introyección de culpa)
- Las relaciones públicas en Twitter con ciertas personas tienen un contexto personal que los críticos desconocen
- Quien difunde esos ...

**5.** `0.2500` | *mitología y religión* | Orfeo y Eurídice [44:03]
   🐍 La muerte de Eurídice: lo salvaje como peligro sin aviso
   - Eurídice huía de un pastor fauno que la quería raptar, representante de lo pueblerino y rústico
- Es mordida por una serpiente: símbolo de cómo lo salvaje es peligroso sin aviso, sin motivo y sin razón
- La muerte de Eurídice no tiene mor...

### Dense+Reranker top-5

**1.** `0.1971` | *análisis de obra* | Análisis arquetípico La Bruja [45:22]  **<- chunk fuente**
   📜 El Malleus Maleficarum y la personificación del mal
   - El tratado sobre brujería recopilaba ritos alejandrinos, paganos y leyenda popular, y tuvo bula papal
- Las brujas untaban palos con sustancias enteógenas que absorbidas por mucosas provocaban viajes alucinatorios — origen de "montar en e...

**2.** `0.0024` | *análisis de obra* | Análisis arquetípico La Bruja [1:55:35]
   📖 El pacto con el diablo: la firma del libro y el vuelo
   - El diablo la tienta con cosas que no pertenecen al mundo del trabajo ni de lo real — la mujer intercambia lo civilizatorio por lo absolutamente ideal
- Ella no sabe escribir su nombre; el diablo dice "yo guiaré tu mano" — para pecar no ne...

**3.** `0.0015` | *análisis de obra* | Análisis: Nosferatu (Eggers, 2024). El último Mito Polar [2:28:13]
   🌅 El sacrificio de la diosa: la profecía y el engaño final
   - Von Franz lee la profecía: la doncella ofreció su amor a la bestia liberándonos de Nosferatu; ella es la cura
- Ellen engaña a Thomas enviándolo a cazar formas del mal que no son las originarias: el verdadero mal está en el sacrificio
- L...

**4.** `0.0006` | *análisis de obra* | No entendiste Anticristo. Análisis arquetípico de Anticristo [1:18:30]
   📷 La tesis sobre el genocidio de brujas y el mal en lo femenino
   - Ella vino a Edén a escribir su tesis sobre casos reales de brujería y el genocidio contra mujeres
- El caso de Johann Prentice: una bruja que alimentaba a su familiar con su propia sangre y confesó haber pedido que hiciera daño a un niño
...

**5.** `0.0006` | *análisis de obra* | Análisis arquetípico de Los Rescatadores [29:41]
   🧙‍♀️ La bruja como arquetipo de lo femenino desligado del orden
   - La bruja es lo femenino que se ha separado de la comunidad, la familia y la moral para seguir su propio camino
- Un interior muerto lleno de pecado donde no puede nacer nada nutritivo es lo que define a la bruja fabulosa
- La niña custodi...

---

## q13 -- *adversarial_colloquial* -- cultura y actualidad

> **el rollo ese de Diddy y los raperos que palmaron de los 90**

_Hipótesis: Coloquial sin nombres propios (Tupac/Notorious). Reranker debería leer 'raperos 90' + 'Diddy' juntos y entender contexto._

_Posición chunk fuente_: dense20=6 | dense5=fuera | RRF5=5 | reranker5=2

### Dense top-5

**1.** `0.5224` | *cultura y actualidad* | La Batalla Espiritual [53:38]
   👑 Beyoncé y Jay-Z como presuntos cómplices
   - Jay-Z era colega de Diddy desde los 90, iban juntos a todas partes como sus "segundos"
- La canción "She Knows" de J. Cole acusa de forma encriptada a Beyoncé de saberlo todo
- La rapera Jaguar Wright acusó directamente a Beyoncé y Jay-Z ...

**2.** `0.4680` | *cultura y actualidad* | La Batalla Espiritual [42:28]
   🔫 El tiroteo en la fiesta de Shine y la relación con Jennifer López
   - En una fiesta de presentación del disco de Shine (producido por Diddy) hubo un tiroteo dentro de la discoteca
- Shine cargó con toda la culpa y pasó 8 años en cárcel; después declaró que el arma era de Diddy
- Se rumorea que el FBI habría...

**3.** `0.4632` | *cultura y actualidad* | La Batalla Espiritual [46:01]
   🎉 Las fiestas de Diddy: White Parties y Freak Out Parties
   - Las White Parties eran eventos de alto perfil donde asistían Leonardo DiCaprio, Ashton Kutcher, Trump, Michael Jackson — no eras nadie si no estabas invitado
- Las Freak Out Parties se hacían en suites de hotel sin móviles; había habitaci...

**4.** `0.4565` | *cultura y actualidad* | La Batalla Espiritual [1:29:35]
   😢 Justin Bieber como víctima del sistema
   - Usher, que vivió con Diddy desde los 13 años bajo custodia legal, produjo el primer single de Bieber ("Baby")
- Diddy buscó la custodia de Bieber (los padres no se la dieron) y pasaba mucho tiempo con él; existen vídeos incómodos de Diddy...

**5.** `0.4549` | *cultura y actualidad* | La Batalla Espiritual [27:49]
   🔍 Caso P. Diddy: los hechos formales y acusaciones
   - Una exnovia (Cassie Ventura) le denunció en 2023 por maltrato hardcore, existe vídeo de cámaras de seguridad pegándola en un hotel
- Se le acusa de obligar a parejas a tomar drogas, mantener relaciones con terceros estando drogadas, y gra...

### RRF top-5

**1.** `1.0000` | *cultura y actualidad* | La Batalla Espiritual [53:38]
   👑 Beyoncé y Jay-Z como presuntos cómplices
   - Jay-Z era colega de Diddy desde los 90, iban juntos a todas partes como sus "segundos"
- La canción "She Knows" de J. Cole acusa de forma encriptada a Beyoncé de saberlo todo
- La rapera Jaguar Wright acusó directamente a Beyoncé y Jay-Z ...

**2.** `0.5000` | *cultura y actualidad* | La Batalla Espiritual [27:49]
   🔍 Caso P. Diddy: los hechos formales y acusaciones
   - Una exnovia (Cassie Ventura) le denunció en 2023 por maltrato hardcore, existe vídeo de cámaras de seguridad pegándola en un hotel
- Se le acusa de obligar a parejas a tomar drogas, mantener relaciones con terceros estando drogadas, y gra...

**3.** `0.4762` | *cultura y actualidad* | La Batalla Espiritual [42:28]
   🔫 El tiroteo en la fiesta de Shine y la relación con Jennifer López
   - En una fiesta de presentación del disco de Shine (producido por Diddy) hubo un tiroteo dentro de la discoteca
- Shine cargó con toda la culpa y pasó 8 años en cárcel; después declaró que el arma era de Diddy
- Se rumorea que el FBI habría...

**4.** `0.4500` | *cultura y actualidad* | La Batalla Espiritual [46:01]
   🎉 Las fiestas de Diddy: White Parties y Freak Out Parties
   - Las White Parties eran eventos de alto perfil donde asistían Leonardo DiCaprio, Ashton Kutcher, Trump, Michael Jackson — no eras nadie si no estabas invitado
- Las Freak Out Parties se hacían en suites de hotel sin móviles; había habitaci...

**5.** `0.3929` | *cultura y actualidad* | La Batalla Espiritual [37:25]  **<- chunk fuente**
   🎤 Diddy como productor musical y la rivalidad costa este-oeste
   - Diddy fundó el sello Bad Boy Records y prácticamente todo lo que tocaba se convertía en oro como productor
- Siempre se rumoreó que ordenó el asesinato de Tupac; poco después también murió tiroteado Notorious B.I.G.
- Se rumorea que Diddy...

### Dense+Reranker top-5

**1.** `0.3509` | *cultura y actualidad* | La Batalla Espiritual [53:38]
   👑 Beyoncé y Jay-Z como presuntos cómplices
   - Jay-Z era colega de Diddy desde los 90, iban juntos a todas partes como sus "segundos"
- La canción "She Knows" de J. Cole acusa de forma encriptada a Beyoncé de saberlo todo
- La rapera Jaguar Wright acusó directamente a Beyoncé y Jay-Z ...

**2.** `0.0165` | *cultura y actualidad* | La Batalla Espiritual [37:25]  **<- chunk fuente**
   🎤 Diddy como productor musical y la rivalidad costa este-oeste
   - Diddy fundó el sello Bad Boy Records y prácticamente todo lo que tocaba se convertía en oro como productor
- Siempre se rumoreó que ordenó el asesinato de Tupac; poco después también murió tiroteado Notorious B.I.G.
- Se rumorea que Diddy...

**3.** `0.0116` | *cultura y actualidad* | La Batalla Espiritual [1:29:35]
   😢 Justin Bieber como víctima del sistema
   - Usher, que vivió con Diddy desde los 13 años bajo custodia legal, produjo el primer single de Bieber ("Baby")
- Diddy buscó la custodia de Bieber (los padres no se la dieron) y pasaba mucho tiempo con él; existen vídeos incómodos de Diddy...

**4.** `0.0078` | *cultura y actualidad* | La Batalla Espiritual [46:01]
   🎉 Las fiestas de Diddy: White Parties y Freak Out Parties
   - Las White Parties eran eventos de alto perfil donde asistían Leonardo DiCaprio, Ashton Kutcher, Trump, Michael Jackson — no eras nadie si no estabas invitado
- Las Freak Out Parties se hacían en suites de hotel sin móviles; había habitaci...

**5.** `0.0072` | *cultura y actualidad* | La Batalla Espiritual [1:05:49]
   🎵 Britney Spears como posible víctima de Diddy
   - Las primeras veces que pillaron a Britney en escándalos salía de fiestas de Diddy; ella siempre dijo que le pusieron algo en la bebida
- En la gala MTV 2007 hay vídeos de ella perfectamente en ensayos y completamente ida después
- Se sugi...

---

## q14 -- *adversarial_paraphrase* -- filosofía y teoría

> **diferencia entre soñar despierto sabiendo que no pasa y querer algo de verdad**

_Hipótesis: Paráfrasis muy distante de fantasía/anhelo en lenguaje cotidiano. Estresa abstracción._

_Posición chunk fuente_: dense20=18 | dense5=fuera | RRF5=fuera | reranker5=4

### Dense top-5

**1.** `0.5717` | *análisis de obra* | El Sueño Eterno: Análisis Arquetípico de la Bella Durmiente. [1:03:26]
   🎵 Las dos versiones de la canción: deseo versus profecía
   - La versión de 1959 habla de idealización romántica: el fuego encendido, la ensoñación que quiere hacerse realidad
- La segunda versión habla de la profecía misma: "sé que un sueño es difícil realizar, más yo tengo fe en que despertaré"
- ...

**2.** `0.5691` | *cultura y actualidad* | El Hate Bombing de la izquierda. [59:44]
   💭 Diferencias de género en los sueños: objetos vs. vínculos
   - Los hombres sueñan más con objetos y mecanismos, las mujeres con interacciones sociales (excluyendo sexo y agresión)
- "Interacciones sociales" se traduce mejor como "vínculos" porque el sexo y la agresión no son vínculos sino relaciones ...

**3.** `0.5606` | *filosofía y teoría* | ¿Qué es un símbolo? (Parte 1: filosofía vs poética) [54:10]
   🙏 Diferencia entre rezar y desear: magia vs. religión
   - La magia quiere conseguir poder y que se cumplan los anhelos; rezar consiste en entregarse a la voluntad divina renunciando a todo anhelo
- Rezar es un diálogo con la divinidad que puede ser verbal, afectivo o imaginario
- Detrás de todo ...

**4.** `0.5517` | *filosofía y teoría* | Último Stream del Año [47:09]
   💤 Diferencia cualitativa entre estados de conciencia: vigilia y sueño
   - No se puede decir que el sueño sea "menos conciencia" porque no se puede cuantificar esa diferencia
- Si conciencia equivale a experiencia, seguimos sin poder definir qué es experiencia-conciencia
- La conciencia no funciona como un dial ...

**5.** `0.5478` | *psicología* | Psicoanálisis de la orientación política: Dime a quién votas y te diré quién es tu madre. [19:14]
   💔 Anhelos, carencias y heridas fundamentales
   - Un anhelo es un deseo que depende de las carencias: se anhela aquello que no se tiene
- Las cosas tienen más importancia cuando no se poseen que cuando sí, porque la importancia es significado afectivo
- Las heridas fundamentales pueden s...

### RRF top-5

**1.** `0.5000` | *análisis de obra* | El Sueño Eterno: Análisis Arquetípico de la Bella Durmiente. [1:03:26]
   🎵 Las dos versiones de la canción: deseo versus profecía
   - La versión de 1959 habla de idealización romántica: el fuego encendido, la ensoñación que quiere hacerse realidad
- La segunda versión habla de la profecía misma: "sé que un sueño es difícil realizar, más yo tengo fe en que despertaré"
- ...

**2.** `0.5000` | *filosofía y teoría* | ¿Porqué el amor? Introducción: Libertad y lo que Surja [2:16:57]
   💊 Matrix y la elección entre verdad sufriente e ignorancia feliz
   - La diferencia entre el aspecto libertario y el conservador es que hacia arriba en el diagrama es preferible la verdad sufriente y hacia abajo la ignorancia feliz
- Cifra en Matrix elige el autoengaño porque la realidad fuera de Matrix era...

**3.** `0.3333` | *cultura y actualidad* | El Hate Bombing de la izquierda. [59:44]
   💭 Diferencias de género en los sueños: objetos vs. vínculos
   - Los hombres sueñan más con objetos y mecanismos, las mujeres con interacciones sociales (excluyendo sexo y agresión)
- "Interacciones sociales" se traduce mejor como "vínculos" porque el sexo y la agresión no son vínculos sino relaciones ...

**4.** `0.3333` | *psicología* | (segunda) Entrevista a Unicornio Psicópata [36:45]
   ⚡ Diferencia entre esquizoide y esquizotípico: querer y no poder
   - El esquizoide no tiene necesidad de relacionarse; el esquizotípico sí la tiene pero le aterra hacerlo
- El miedo que siente al relacionarse es comparable al pánico del desembarco de Normandía, no a un examen
- Su mente le dice que salga c...

**5.** `0.3333` | *mitología y religión* | El mito del Gólem: Transhumanismo [25:29]
   🚀 Ciencia ficción como la mejor fantasía posible
   - La mejor fantasía es la que más verdad contiene pareciendo lo contrario
- La diferencia entre ciencia ficción y cuento de hadas reside en el presupuesto de plausibilidad: técnica versus magia
- Alien es la forma más original de hablar de ...

### Dense+Reranker top-5

**1.** `0.0439` | *mitología y religión* | ¿Qué es la magia? [1:03:51]
   👁️ Alucinación frente a ilusión: episodios y conciencia
   - La alucinación es vivir algo inexistente creyendo que es real; es episódica
- La ilusión es percibir algo sabiendo que no puede ser cierto; se mantiene la conciencia de irrealidad
- Epifanía no es iluminación: es un proceso cognitivo univ...

**2.** `0.0230` | *psicología* | ¡Inside Proxy está emitiendo en directo! [1:07:29]
   🌟 "Puedes ser todo lo que quieras" y "Todo lo que quieres es absurdo"
   - Al joven se le dice simultáneamente que puede ser todo lo que quiera y que todo lo que quiere es infantil e irrealizable
- "Sueña alto" y "deja de soñar" coexisten como mandatos contradictorios
- Ejemplo paradigmático: "puedes ser astrona...

**3.** `0.0178` | *psicología* | Friendzone [03:01]
   ⚖️ La asimetría real: querer más vs. querer menos
   - Los amigos no se merecen, se tienen o no se tienen
- El hombre que quiere algo romántico quiere más de lo que ya tiene, no menos
- La mujer que solo quiere amistad quiere menos de lo que el hombre ofrece, lo cual invierte la acusación de ...

**4.** `0.0131` | *filosofía y teoría* | Inteligencia Real e Inteligencia Artificial [1:00:05]  **<- chunk fuente**
   🌀 Fantasía, anhelo y futuro como categorías afectivas
   - La fantasía es una ficción que sabemos imposible y en la que nos quedamos sin forzar que ocurra
- El cambio a la adultez es saber que no es posible alcanzar cierta ficción y llamarla fantasía
- El futuro deseable es aquel que voy a intent...

**5.** `0.0121` | *filosofía y teoría* | ¿Qué es un símbolo? (Parte 1: filosofía vs poética) [54:10]
   🙏 Diferencia entre rezar y desear: magia vs. religión
   - La magia quiere conseguir poder y que se cumplan los anhelos; rezar consiste en entregarse a la voluntad divina renunciando a todo anhelo
- Rezar es un diálogo con la divinidad que puede ser verbal, afectivo o imaginario
- Detrás de todo ...

---

## q15 -- *adversarial_colloquial* -- análisis de obra

> **como te encariñas con elsa de frozen viendo que se siente culpable de hacer daño**

_Hipótesis: Coloquial + nombre propio mezclado con paráfrasis de identificación emocional. Test mixto._

_Posición chunk fuente_: dense20=1 | dense5=1 | RRF5=1 | reranker5=1

### Dense top-5

**1.** `0.6387` | *análisis de obra* | Análisis arquetípico Frozen [1:09:24]  **<- chunk fuente**
   🧊 El accidente y la semilla de culpa: Elsa como portadora de una maldición autoimpuesta
   - Jugando con el hielo Elsa hiere a Ana sin querer y algo completamente maravilloso se convierte en algo peligroso
- Cuanto peor se siente Elsa más frío lanza: su don hace daño a los demás y desde muy pequeña se siente culpable porque cree ...

**2.** `0.6234` | *análisis de obra* | Análisis arquetípico Frozen [1:26:03]
   🧤 Los guantes de Elsa: la culpa como creencia de que tu don es una maldición
   - La culpa es la creencia de que algo que está en ti es malo y ha hecho mal, y si lo repites volverás a hacerlo mal
- Cuando la culpa no proviene solo del arrepentimiento sino que está reforzada desde fuera, al darte cuenta de que no es así...

**3.** `0.6112` | *análisis de obra* | Análisis arquetípico Frozen [1:50:17]
   🏔️ El castillo de hielo como herida narcisista: empoderamiento sin arreglar nada
   - Elsa construye otro yo de hielo que no va a sentir nunca más porque cuando siente la gente la culpabiliza
- El empoderamiento consiste en no arreglar nada de lo que te ha llevado a ser como eres pero decidir que nada de aquello te importa...

**4.** `0.6050` | *análisis de obra* | Análisis arquetípico Frozen [1:14:27]
   🪞 Frozen como espejo de la herida narcisista: identificación con la víctima incomprendida
   - Disney consigue que toda persona con una idea de infancia en la que fue el centro incomprendido de un conflicto se identifique mágicamente con Elsa
- El héroe nunca tiene poder ilimitado desde el principio; tiene que hacérselo merecer, pe...

**5.** `0.5574` | *análisis de obra* | Olaf y la jaula de oro [00:00]
   🧊 Frozen como mapa intrapsíquico: todos los personajes son partes del mismo yo
   - Todos los personajes de Frozen pueden leerse como partes de una misma psique, igual que en Inside Out
- Elsa y Ana son la misma persona: Elsa es la herida y Ana es la parte no afectada que puede relacionarse con el mundo
- Olaf representa...

### RRF top-5

**1.** `1.0000` | *análisis de obra* | Análisis arquetípico Frozen [1:09:24]  **<- chunk fuente**
   🧊 El accidente y la semilla de culpa: Elsa como portadora de una maldición autoimpuesta
   - Jugando con el hielo Elsa hiere a Ana sin querer y algo completamente maravilloso se convierte en algo peligroso
- Cuanto peor se siente Elsa más frío lanza: su don hace daño a los demás y desde muy pequeña se siente culpable porque cree ...

**2.** `0.6667` | *análisis de obra* | Análisis arquetípico Frozen [1:26:03]
   🧤 Los guantes de Elsa: la culpa como creencia de que tu don es una maldición
   - La culpa es la creencia de que algo que está en ti es malo y ha hecho mal, y si lo repites volverás a hacerlo mal
- Cuando la culpa no proviene solo del arrepentimiento sino que está reforzada desde fuera, al darte cuenta de que no es así...

**3.** `0.3167` | *análisis de obra* | Análisis arquetípico de Inocencia interrumpida [2:02:12]
   🌅 El punto de inflexión: Susana actúa como adulta
   - En lugar de huir del dolor empeorando su vida, Susana espera a que se pase el dolor por primera vez
- Comprende la frase del primer médico: "estás haciendo daño a la gente que te rodea aunque no te das cuenta"
- Ha tenido que morir alguie...

**4.** `0.2500` | *análisis de obra* | Análisis arquetípico Frozen [1:50:17]
   🏔️ El castillo de hielo como herida narcisista: empoderamiento sin arreglar nada
   - Elsa construye otro yo de hielo que no va a sentir nunca más porque cuando siente la gente la culpabiliza
- El empoderamiento consiste en no arreglar nada de lo que te ha llevado a ser como eres pero decidir que nada de aquello te importa...

**5.** `0.2500` | *análisis de obra* | Análisis arquetípico Frozen [1:14:27]
   🪞 Frozen como espejo de la herida narcisista: identificación con la víctima incomprendida
   - Disney consigue que toda persona con una idea de infancia en la que fue el centro incomprendido de un conflicto se identifique mágicamente con Elsa
- El héroe nunca tiene poder ilimitado desde el principio; tiene que hacérselo merecer, pe...

### Dense+Reranker top-5

**1.** `0.7541` | *análisis de obra* | Análisis arquetípico Frozen [1:09:24]  **<- chunk fuente**
   🧊 El accidente y la semilla de culpa: Elsa como portadora de una maldición autoimpuesta
   - Jugando con el hielo Elsa hiere a Ana sin querer y algo completamente maravilloso se convierte en algo peligroso
- Cuanto peor se siente Elsa más frío lanza: su don hace daño a los demás y desde muy pequeña se siente culpable porque cree ...

**2.** `0.4116` | *análisis de obra* | Análisis arquetípico Frozen [1:26:03]
   🧤 Los guantes de Elsa: la culpa como creencia de que tu don es una maldición
   - La culpa es la creencia de que algo que está en ti es malo y ha hecho mal, y si lo repites volverás a hacerlo mal
- Cuando la culpa no proviene solo del arrepentimiento sino que está reforzada desde fuera, al darte cuenta de que no es así...

**3.** `0.2486` | *análisis de obra* | Análisis arquetípico Frozen [1:50:17]
   🏔️ El castillo de hielo como herida narcisista: empoderamiento sin arreglar nada
   - Elsa construye otro yo de hielo que no va a sentir nunca más porque cuando siente la gente la culpabiliza
- El empoderamiento consiste en no arreglar nada de lo que te ha llevado a ser como eres pero decidir que nada de aquello te importa...

**4.** `0.0226` | *análisis de obra* | Análisis: Nosferatu (Eggers, 2024). El último Mito Polar [29:17]
   🌑 La escena inicial: el pecado prematuro y el pacto con el diablo
   - La niña ruega perdón por su pecado: conoció el pecado muy temprano y se siente culpable
- El mal le susurra "tú me despertaste de una eternidad de oscuridad": la culpa le dice que ella es la causa de su propio pecado
- "No eres para el mu...

**5.** `0.0220` | *análisis de obra* | Análisis arquetípico de Inocencia interrumpida [2:09:16]
   👑 La reina negra y la reina blanca: la integración final
   - Lisa y Susana separadas por una puerta representan la parte tóxica y la parte salvable de la enfermedad
- Lisa dice "hago el papel de villana como tú querías": habla con su propia enfermedad, con su madre
- La esencia del trastorno de Lis...

---

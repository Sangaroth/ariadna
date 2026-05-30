"""Prompts de sumarización + validación, generalizados de ProxySummaries.

El sumario de un paper es análogo al de un vídeo: índice temático con un marker de
POSICIÓN por tema. Vídeo → `[MM:SS]`; paper → `[p.NN]`. La salida del paper usa
`- p.NN 🎭 Título` (el `PaperAdapter.summary_marker_re()` la re-parsea a chunks).
"""

from __future__ import annotations

import re

SUMMARY_PROMPT_PAPER_ES = """\
Eres un analista experto en literatura científica. Tu tarea es crear un índice \
temático del siguiente paper, fiel al texto y orientado a recuperación.

## Instrucciones

A partir del texto del paper (con marcas de página [p.NN]) genera un índice temático:

1. **Identifica los temas/argumentos principales** en el orden en que aparecen \
   (introducción, métodos, resultados, discusión, conclusiones — según el paper).
2. **Usa SOLO números de página que aparezcan** como marcas [p.NN] en el texto. \
   Asigna a cada tema la página donde realmente empieza.
3. **Títulos sustantivos**: cada título captura la tesis/contribución concreta, \
   no una descripción genérica. Bueno: "La teleosemántica deriva contenido de la \
   función biológica". Malo: "Se habla de teleosemántica".
4. **2-4 detalles por tema**: afirmaciones concretas del paper (hallazgos, claims, \
   definiciones), no descripciones vagas.
5. **Un emoji temático** por sección.
6. **Las páginas deben ser crecientes** (cada tema empieza en página >= al anterior).
7. **Ignora** cabeceras/pies de página, agradecimientos y la lista de referencias.

## Formato de salida EXACTO

```
- p.1 🧠 Título sustantivo del tema

  - Afirmación concreta 1,
  - Afirmación concreta 2,
  - Afirmación concreta 3,

- p.4 🔬 Siguiente tema sustantivo

  - Detalle concreto 1,
  - Detalle concreto 2,
```

## Restricciones

- NO inventes ni infieras información que no esté explícitamente en el paper.
- NO uses frases como "En esta sección se habla de..." o "Se discute sobre...".
- Los números de página DEBEN corresponder a marcas [p.NN] reales del texto.
- Genera SOLO el índice, sin preámbulo ni conclusión. \
Tu respuesta debe empezar DIRECTAMENTE con "- p.NN" del primer tema.

## Datos del paper

**Título:** {title}
**Páginas:** {n_pages}

## Texto del paper (con marcas de página)

{text}
"""

# Marker de tema de un sumario de paper: "- p.7 🎭 Título" (sección opcional "p.7s3.2").
PAPER_TOPIC_RE = re.compile(r"^- p\.(\d+)(?:s[\w.]+)?\s", re.MULTILINE)

# Artefactos de LLM que invalidan un sumario (compartido entre fuentes).
_ARTIFACT_PATTERNS = [
    r"como modelo de lenguaje", r"como asistente de ia", r"soy una? (?:ia|asistente|modelo)",
    r"no puedo ayudarte", r"en esta sección se habla", r"en este segmento",
]


def validate_summary(
    summary: str,
    topic_re: re.Pattern[str] = PAPER_TOPIC_RE,
    to_ordinal=lambda m: int(m),
    min_topics: int = 3,
    max_topics: int = 80,
    max_ordinal: int | None = None,
) -> list[str]:
    """Valida un sumario generado. Devuelve lista de problemas (vacía = válido).

    Generalizado: `topic_re` captura en group(1) el token de posición de cada tema;
    `to_ordinal` lo convierte a int para chequear monotonía. Defaults = paper (p.NN).
    """
    issues: list[str] = []
    topics = topic_re.findall(summary)
    if not topics:
        issues.append("No se encontraron temas con marca de posición")
        return issues

    n = len(topics)
    if n < min_topics:
        issues.append(f"Muy pocos temas: {n} (mínimo {min_topics})")
    if n > max_topics:
        issues.append(f"Demasiados temas: {n} (máximo {max_topics})")

    prev = -1
    for tok in topics:
        ordv = to_ordinal(tok)
        if ordv < prev:
            issues.append(f"Posición no creciente: {tok} (tras {prev})")
        prev = ordv
        if max_ordinal is not None and ordv > max_ordinal:
            issues.append(f"Posición {tok} excede el máximo ({max_ordinal})")

    # Bullets por tema: slice entre headers (robusto a grupos de captura del regex).
    matches = list(topic_re.finditer(summary))
    for i, m in enumerate(matches, 1):
        start = m.end()
        end = matches[i].start() if i < len(matches) else len(summary)
        bullets = re.findall(r"^\s+- .+", summary[start:end], re.MULTILINE)
        if len(bullets) < 2:
            issues.append(f"Tema {i} tiene {len(bullets)} detalle(s) (mínimo 2)")

    lower = summary.lower()
    for pat in _ARTIFACT_PATTERNS:
        m = re.search(pat, lower)
        if m:
            issues.append(f"Artefacto de LLM: '{m.group()}'")

    return issues

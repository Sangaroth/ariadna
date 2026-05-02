# Postmortem 2026-05-02 — Bucle Karpathy mal diseñado

> Fallo de diseño detectado tras 100 vídeos procesados con resultado no usable. Documento las causas, qué aprendimos del Karpathy real, y los principios que guían el rediseño. **No defiende el trabajo invertido**.

---

## 1. Qué se intentó

Implementar el patrón Karpathy "LLM Wiki" ([gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)) sobre el corpus YouTube de Proxy: un wiki estructurado en markdown que se enriquece automáticamente cada vez que llega un source nuevo (vídeo). Las 11 páginas seed iniciales se compilaron a mano antes de adoptar este enfoque; el push-based debía escalar al corpus de 296 vídeos sin re-compilación manual.

## 2. Qué se entregó (mañana del 2026-05-02)

- `scripts/extract_video_themes.py` — extractor que produce JSON estructurado por vídeo (entities, pending_updates, promote_queue, thesis_candidates, discarded)
- `scripts/apply_pending_updates.py` — aplica `pending_updates` al wiki con 4 ops diff-style (insert_after_passage, replace_passage, etc.) y anchor literal único como regla de seguridad
- `scripts/overnight_run.py` — orquestador batch (lotes de 5: extract → aggregate → commit → apply → commit → housekeeping → loop)
- `scripts/extract_incremental.py` — wrapper para vídeos nuevos vs `processed_videos.json`
- `wiki/_meta/scope.md` — alcance editorial (3ª capa Karpathy)
- `wiki/_meta/canonical_whitelist.json` — figuras/frameworks/obras canónicas
- `docs/EXTRACTION_PIPELINE.md` — doc maestro del pipeline
- 75+ commits de actualizaciones a las 11 páginas seed durante el overnight

## 3. Resultado real tras 28 batches del overnight (100 vídeos procesados)

| Métrica | Valor | Interpretación |
|---|---|---|
| Páginas wiki tras overnight | 11 (mismas) | Cero páginas nuevas creadas |
| Páginas modificadas | 8 de 11 | Inserts crudos pegados sin curaduría editorial |
| Inserts aplicados | 57 | Fragmentos cross-vídeos sin reorganizar |
| Candidatos a página nueva en cola | 80 únicos / 100 propuestas | Cola sin compilar — sin valor inmediato |
| Wikilinks rotos nuevos en cuerpo | 3 | Daño contenido por respeto a hard rules |
| Wikilinks rotos pre-existentes | 14 | No resueltos (mito-solar, mito-lunar, matrix, peter-pan, man-of-steel) |
| Ratio promote_new / update_existing | 100 / 57 | El extractor ve más entidades NUEVAS que actualizaciones — wiki infraconstruido respecto al corpus |

**El veredicto del usuario fue correcto**: "el resultado es golem, feo y poco práctico, no ordenado".

## 4. El error de diseño (causa raíz)

### 4.1 Confundí "ingest" con "extract + apply diff"

Karpathy describe ingest como:

> *"reads it, extracts the key information, and integrates it into the existing wiki — **updating entity pages, revising topic summaries**"*

Las palabras críticas que ignoré:

- **"updating entity pages"** — implica REWRITE coherente de la página completa, no append de párrafos al final
- **"revising topic summaries"** — "revising" implica reorganización editorial, no concatenación
- **"integrates"** — fusión, no acumulación

Lo que implementé:

- Extract → produce JSON con `pending_updates: [{section_target, content_proposed}]`
- Apply → inserta `content_proposed` tras el anchor único en la página existente

Resultado: un párrafo del extractor del vídeo K se pega al final de la sección X. Otro párrafo del vídeo K+1 se pega después del anterior. Sin re-leer lo previo, sin reorganizar, sin priorizar. **Append crudo, no integración**.

### 4.2 Diferí compile como "Sprint posterior"

En `EXTRACTION_PIPELINE.md` §7.2 escribí:

> *"`scripts/compile_wiki_pages.py`: vacía `promote_queue.json` compilando páginas nuevas... Sin esto, los candidatos a página nueva quedan en cola indefinidamente"*

Y aún así dejé que el overnight corriera. Error de juicio: tras solo 4 vídeos del piloto era tolerable; tras 100 es estructuralmente roto.

**Compile NO es Sprint posterior. Es la operación primaria del ingest Karpathy** — junto al rewrite de páginas existentes. Sin compile, las cross-references son pointers a vacío y el "compounding artifact" no compone.

### 4.3 Decoré apply diff-style como herramienta principal

Las 4 ops diff-style (insert_after_passage, etc.) están bien diseñadas: anchor literal único + skip seguro si ambiguo + backup automático. Pero estas son herramientas **para correcciones humanas asistidas** o ajustes finos, NO para ingestar 100 vídeos contra 11 páginas.

Para ingest masivo lo correcto es rewrite por página, agrupando todos los inputs cross-source que tocan esa página.

### 4.4 Métrica de éxito del extractor mal calibrada

Definí "éxito" del extractor como "produce un JSON válido con decisiones bien justificadas y citas literales". El extractor cumplía eso al 95%. Pero esa NO ES la métrica correcta para ingest.

La métrica correcta es: **¿la página resultante es coherente como wiki?** Esa pregunta no la formulé hasta ver el resultado de las 8 páginas modificadas.

## 5. Lo que aprendimos del Karpathy real

Re-leyendo el gist con la experiencia ganada del error, los matices que ahora reconozco:

| Frase | Lo que ignoré | Lo que significa |
|---|---|---|
| *"updating entity pages, revising topic summaries"* | "updating" como append | Rewrite coherente página por página |
| *"the cross-references are already there"* | Diferí compile | Cross-refs requieren páginas referenciadas EXISTENTES al momento del ingest |
| *"synthesis already reflects everything you've read"* | Acumulación de inserts | El wiki ES la síntesis, cada source la actualiza coherente |
| *"the cost of maintenance is near zero"* | Dejé crecer cola | Coste cero solo si el ingest mantiene coherencia. Si genera golem, mantenimiento = enorme |
| *"Lint operations: contradictions, stale info, orphaned pages"* | No implementé lint | Sin lint, el ingest puede plantar contradicciones que se sedimentan |

El Karpathy real es más exigente en COHERENCIA editorial de lo que parece a primera lectura. La palabra "wiki" no es decoración; implica compromiso con la estructura editorial unificada por página, lo cual hace que la operación canónica sea rewrite, no append.

## 6. Principios para el rediseño

Sin propuesta de implementación específica todavía — solo los principios que el rediseño debe respetar:

### 6.1 Operación primaria = rewrite por página, no append por source

Ingestar N sources → identificar las páginas afectadas (existentes + nuevas) → rewrite cada página coherente fusionando seed + todo el material cross-source que la toca.

### 6.2 Extract y compile son fases distintas, ambas necesarias

- **Extract** sigue siendo válido: produce decisions estructuradas por source. Es barato, cacheable, escalable.
- **Compile** es la fase que faltaba: agrupa decisions por página afectada, recolecta source summaries relevantes, produce el .md coherente.

Apply diff-style queda RELEGADO a herramienta de correcciones humanas asistidas, no a ingest.

### 6.3 Compile debe ser por página, no por source

Si un concepto X aparece en 50 sources, NO se hacen 50 rewrites consecutivos de X. Se hace UN rewrite que toma todos los inputs acumulados de los 50 sources y produce una página coherente. Coste acotado.

### 6.4 El bucle correcto

```
Para un batch de N sources nuevos:

  1. EXTRACT: extract_video_themes para cada source → N JSONs estructurados
  2. AGGREGATE por página: agrupa decisions y promote_queue por página afectada
  3. COMPILE por página: para cada página afectada, rewrite coherente
       - Si la página ya existe: inputs = seed actual + decisions del batch
       - Si la página es nueva: inputs = decisions + summaries source completos
  4. WRITE atómico: actualizar wiki/<type>/<page_id>.md
  5. LINT cross-page (opcional pero recomendado): detect contradictions, broken refs
  6. COMMIT con mensaje semántico
```

### 6.5 Tamaño del batch importa

Demasiado pequeño (1 source/batch) → muchos rewrites, perdiendo material acumulado entre batches.

Demasiado grande (100 sources/batch) → contexto del LLM saturado, output del rewrite incoherente.

Sweet spot probable: 10-25 sources/batch. Cada página recibe un puñado de inputs por batch, suficiente para rewrite informado pero no abrumador.

### 6.6 Apply diff-style queda conservado pero re-posicionado

`apply_pending_updates.py` con sus 4 ops + anchor único + auto-commit es una herramienta valiosa para:

- Correcciones puntuales humanas ("este chunk debería citar este otro vídeo")
- Refutar lagunas tras revisión humana
- Apply de updates sugeridos por el extractor en tooling interactivo (futuro)

NO se usa en el ingest masivo. Se usa cuando el humano (o un agente futuro) propone una corrección concreta y verificable.

### 6.7 Métrica de éxito del ingest = coherencia editorial post-rewrite

Tras cada batch:

- ¿Las páginas afectadas siguen leyéndose como wiki coherente o son frankenstein?
- ¿Los wikilinks introducidos resuelven a páginas existentes?
- ¿La estructura editorial (Definición → Manifestaciones → Lagunas) se mantiene?

Si no, el rewrite del LLM falló y la página debería marcarse para revisión humana, no aplicarse silenciosamente.

## 7. Decisiones que NO se reabren

A pesar del error de diseño en el bucle, hay piezas validadas que el rediseño conserva:

| Pieza | Estado | Razón |
|---|---|---|
| `scope.md` v0.2 | ✅ Sólido | Contrato editorial bien planteado, no es la fuente del problema |
| `canonical_whitelist.json` v0.1 | ✅ Sólido | Resuelve foundational singletons, palanca correcta |
| `topic_filters.json` | ✅ Sólido | Filtrado declarativo pre-LLM, idea válida |
| Validador de quote_evidence con normalización cosmética | ✅ Bien calibrado tras iteración | Strict reject + normalización funciona |
| Caching cross-call con `--resume` (Anthropic prompt cache) | ✅ Empíricamente verificado (495K cached/sesión) | La palanca de coste funciona |
| Karpathy index slim + Read on-demand | ✅ Diseño correcto | Heavy_context manejable, escalable |
| Cuts de sesión (22 vídeos / 50min / 500K tokens) | ✅ Calibrado | Mantiene cache TTL viable |
| Gitignore opción B (aggregator outputs commited, intermedios local) | ✅ Decisión correcta | Reproducibilidad sin inflar repo |

## 8. Lecciones generalizables más allá de este proyecto

### 8.1 No diferir el componente core

Si la operación canónica de un sistema es X, X no puede ser "Sprint posterior". Diferirlo significa que el sistema NO funciona, no que funciona parcialmente. La diferencia entre "extract + apply" y "extract + apply + compile" no es 33% de funcionalidad — es la diferencia entre "produce datos" y "produce wiki".

### 8.2 Implementar lo más fácil primero es trampa

Apply diff-style (con sus 4 ops, uniqueness check, backup) es estéticamente satisfactoria de implementar. Compile es harder porque requiere LLM rewrite, validación de coherencia editorial, manejo de inputs de múltiples sources. Implementar lo fácil primero te deja con la sensación de progreso mientras la pieza esencial sigue ausente.

### 8.3 Métrica de éxito ≠ métrica del componente

El extractor "funcionaba" por su métrica interna (JSON válido, citas literales). Pero el sistema NO funcionaba por su métrica externa (wiki coherente). El segundo es lo que importa.

### 8.4 La filosofía sin implementación correcta es decoración

Decir "implementamos Karpathy LLM Wiki" tras shippeando extract+apply es overselling. Karpathy real implica rewrite coherente. Sin esa pieza, el patrón no es Karpathy — es algo más débil que comparte solo la nomenclatura.

### 8.5 Coste de errores estructurales escala con el barrido

Un error de diseño que produce 1 página golem es trivial de revertir. El mismo error con 100 páginas afectadas requiere o revertir mucho trabajo o curar a mano. La asimetría favorece **detectar el error con piloto pequeño antes de barrido masivo**. En este caso debí haber visto el problema con el piloto v3 (4 vídeos / 4 páginas modificadas) y haber parado antes del overnight.

## 9. Estado del repo tras este postmortem

- 11 páginas wiki seed restauradas al estado del 2026-05-01 (commit pre-overnight)
- Scripts de extract / apply / overnight / incremental conservados (validados parcialmente)
- `scope.md` y `canonical_whitelist.json` conservados (contrato editorial sólido)
- `compile_wiki_pages.py` eliminado (su versión preliminar tenía el diseño viciado, se re-escribirá tras este postmortem)
- `EXTRACTION_PIPELINE.md` conservado pero **requiere revisión** para alinearse con el rediseño

## 10. Lo que sigue (sin propuesta — solo enumeración)

Tras este postmortem, queda pendiente:

1. **Re-escribir `compile_wiki_pages.py`** con compile como operación primaria por página (no por source)
2. **Re-escribir `overnight_run.py`** para que el bucle sea extract → aggregate → COMPILE → write, no extract → apply → loop
3. **Actualizar `EXTRACTION_PIPELINE.md`** con el bucle correcto
4. **Re-procesar el corpus** con el bucle correcto y validar coherencia editorial post-rewrite

Ninguno de estos pasos se inicia sin acuerdo explícito tras lectura de este documento.

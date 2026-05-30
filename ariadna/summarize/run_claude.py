"""Runner de `claude -p` (subprocess). Portado del patrón de ProxySummaries,
agnóstico de fuente. Devuelve el texto de la respuesta o None tras agotar reintentos.
"""

from __future__ import annotations

import logging
import subprocess
import time

log = logging.getLogger(__name__)


def run_claude(
    prompt: str,
    model: str | None = None,
    retries: int = 2,
    timeout_s: int = 600,
) -> str | None:
    """Pasa `prompt` por la CLI de Claude (`claude -p`) y devuelve la respuesta.

    Sin sesión persistente (cada llamada es independiente). `model` opcional fuerza
    un modelo concreto. Reintenta con backoff lineal. None si falla todo o no hay CLI.
    """
    cmd = ["claude", "-p", "--no-session-persistence"]
    if model:
        cmd += ["--model", model]

    for attempt in range(1, retries + 1):
        proc = None
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            out, err = proc.communicate(input=prompt, timeout=timeout_s)
            if proc.returncode == 0 and out and out.strip():
                return out.strip()
            log.warning("claude -p exit=%s out_empty=%s err=%s",
                        proc.returncode, not (out and out.strip()), (err or "").strip()[:200])
        except FileNotFoundError:
            log.error("CLI `claude` no encontrada en PATH")
            return None
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
            log.warning("claude -p timeout (%ss)", timeout_s)

        if attempt < retries:
            time.sleep(10 * attempt)

    log.error("run_claude: agotados %d intentos", retries)
    return None

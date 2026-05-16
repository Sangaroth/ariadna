#!/bin/bash
# Disparado por cron a las 05:30 del 2026-05-16.
# Lanza un agente Claude autónomo para continuar escribiendo Chunks 2-9
# del plan de implementación multi-tenancy. Self-removing del crontab tras
# ejecutar (one-shot).

set -u

REPO="/home/dae/PycharmProjects/ariadna"
PROMPT_FILE="$REPO/scripts/agent_resume_prompt.md"
LOG_DIR="$REPO/logs"
LOG_FILE="$LOG_DIR/agent_$(date +%Y%m%d_%H%M%S).log"
SELF="$REPO/scripts/resume_plan_chunks_2_9.sh"

cd "$REPO" || { echo "FATAL: cannot cd to $REPO"; exit 1; }
mkdir -p "$LOG_DIR"

# Garantizar PATH para claude CLI (cron strip env)
export PATH="/home/dae/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

{
    echo "============================================================"
    echo "Autonomous agent run starting"
    echo "Date: $(date -Iseconds)"
    echo "Cwd:  $(pwd)"
    echo "Git:  $(git log --oneline -1)"
    echo "Branch: $(git rev-parse --abbrev-ref HEAD)"
    echo "Prompt file: $PROMPT_FILE"
    echo "============================================================"
    echo

    if [ ! -f "$PROMPT_FILE" ]; then
        echo "FATAL: prompt file not found at $PROMPT_FILE"
        exit 1
    fi

    PROMPT="$(cat "$PROMPT_FILE")"

    # claude -p ejecuta el prompt non-interactively y sale al terminar.
    # --dangerously-skip-permissions: sin user para confirmar; el prompt
    #   restringe el alcance ('NO toques' section).
    # --max-turns alto para que el agente pueda completar 8 chunks con
    #   review loop por cada uno.
    claude -p "$PROMPT" \
        --dangerously-skip-permissions \
        --max-turns 500
    EXIT_CODE=$?

    echo
    echo "============================================================"
    echo "Autonomous agent run finished"
    echo "Date: $(date -Iseconds)"
    echo "claude exit code: $EXIT_CODE"
    echo "Git final state:"
    git log --oneline -10
    echo "============================================================"
} 2>&1 | tee -a "$LOG_FILE"

# Self-remove cron entry (one-shot done; no repetir)
( crontab -l 2>/dev/null | grep -v "resume_plan_chunks_2_9.sh" ) | crontab -
echo "Cron entry self-removed. See $LOG_FILE for full output." | tee -a "$LOG_FILE"

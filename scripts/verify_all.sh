#!/usr/bin/env bash
# JCodeQuest 통합 검증 진입점.
#   기본:        sandbox 까지만 (Ollama/OpenAI 미사용)
#   --with-llm:  LLM 경로(정답 코드 → 앙상블, /tutor, /api/runs) 포함
#   --external:  서버를 새로 띄우지 않고 이미 떠 있는 인스턴스에 붙음
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"

# 백엔드 venv가 있으면 우선 사용
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PY="$REPO_ROOT/.venv/bin/python"
fi

exec "$PY" "$REPO_ROOT/scripts/verify_all.py" "$@"

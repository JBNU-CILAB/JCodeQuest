"""Dump OpenAPI specs for a FastAPI app to docs/.

서버를 띄우지 않고 `app.openapi()`를 직접 호출해 JSON을 추출한다.

Usage:
    python scripts/dump_openapi.py backend
    python scripts/dump_openapi.py authoring
    python scripts/dump_openapi.py both     # 한 인터프리터에 두 패키지 의존성이 모두 깔린 환경(CI)

로컬에서는 backend와 authoring_engine 각자의 .venv 의존성이 분리돼 있으므로
보통 `backend` / `authoring` 을 각자의 venv로 한 번씩 호출한다.
CI는 단일 환경에 모두 설치되어 있으므로 `both`로 한 번에 처리한다.

CI는 이 스크립트를 돌린 뒤 `git diff --exit-code`로 drift를 잡는다 — 로컬에서
이 스크립트를 돌리고 결과를 함께 커밋해야 PR이 통과한다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 모듈 임포트 시점에 읽히는 env. 실제 DB/세션을 만지지는 않음.
os.environ.setdefault("SESSION_SECRET_KEY", "openapi-dump-placeholder")
os.environ.setdefault("JCQ_DB_URL", "sqlite:///:memory:")
# dev-login 라우트는 prod-shape 명세에 포함하지 않는다.
# 빈 문자열로 강제 — backend/.env가 1로 켜 둔 경우에도 load_dotenv(override=False)가
# 기존 값을 보존하므로 끌 수 있다.
os.environ["JCQ_AUTH_ALLOW_DEV_STUB"] = ""


def _dump(app, out_path: Path) -> None:
    spec = app.openapi()
    text = json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    out_path.write_text(text, encoding="utf-8")
    print(f"wrote {out_path.relative_to(REPO)} ({len(text)} bytes)")


def _dump_backend() -> None:
    sys.path.insert(0, str(REPO / "backend"))
    try:
        from src.main import app  # type: ignore
        _dump(app, REPO / "docs" / "openapi-backend.json")
    finally:
        sys.path.pop(0)


def _dump_authoring() -> None:
    sys.path.insert(0, str(REPO / "authoring_engine"))
    try:
        from authoring.server import app  # type: ignore
        _dump(app, REPO / "docs" / "openapi-authoring.json")
    finally:
        sys.path.pop(0)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in {"backend", "authoring", "both"}:
        print(__doc__, file=sys.stderr)
        return 2

    (REPO / "docs").mkdir(exist_ok=True)
    target = argv[1]

    if target in ("backend", "both"):
        _dump_backend()
    if target in ("authoring", "both"):
        _dump_authoring()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

"""plagiarism_engine 비동기 호출 헬퍼.

backend 의 first-AC 훅(`apply_grading_event` → `notify_first_ac`)에서 사용한다.
실패는 채점 흐름에 영향을 주면 안 되므로 fire-and-forget + warning 로그만.

설계 노트:
- `JCQ_PLAGIARISM_URL` 미설정 시 no-op — 테스트/로컬에서 plagiarism_engine 없이 backend 만
  띄울 수 있게(테스트가 plagiarism 컨테이너에 의존하지 않음).
- 시크릿은 기존 admin 토큰(`JCQ_ADMIN_TOKEN`) 재사용 — plagiarism_engine 의 admin auth가
  이미 같은 토큰을 받는다.
- httpx.AsyncClient 를 매 호출마다 새로 생성 — 빈도가 낮고(첫 AC만), 모듈 전역 client 의
  lifespan/이벤트루프 누수 위험을 피하기 위함.
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger(__name__)

_TIMEOUT_S = float(os.getenv("JCQ_PLAGIARISM_NOTIFY_TIMEOUT_S", "3.0"))


def _config() -> tuple[str | None, str | None]:
    url = (os.getenv("JCQ_PLAGIARISM_URL") or "").rstrip("/") or None
    token = os.getenv("JCQ_ADMIN_TOKEN") or None
    return url, token


async def notify_first_ac(submission_id: int) -> None:
    """submission 의 첫 AC 가 확정된 직후 plagiarism_engine 에 검사를 트리거.

    fire-and-forget — 응답을 기다리지 않고, 실패도 warning 로그만 남긴다.
    plagiarism_engine 측이 즉시 202 로 반환하고 자기 daemon thread 에서 처리.
    """
    url, token = _config()
    if url is None:
        log.debug("JCQ_PLAGIARISM_URL not set — skip plagiarism notify (sid=%d)", submission_id)
        return
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as cli:
            r = await cli.post(
                f"{url}/api/plagiarism/check-submission",
                headers=headers,
                json={"submission_id": submission_id},
            )
            if r.status_code >= 400:
                log.warning(
                    "plagiarism notify failed sid=%d status=%d body=%s",
                    submission_id, r.status_code, r.text[:200],
                )
    except Exception as e:  # noqa: BLE001 — 모든 실패는 채점 흐름에 영향 없게 흡수
        log.warning("plagiarism notify error sid=%d err=%s", submission_id, e)

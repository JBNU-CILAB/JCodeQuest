"""Dolos(Node) 서브프로세스 래퍼 — 코드 파일들의 구조 유사도 pairwise 산출.

stdin으로 {files:[{id,content}], language} JSON을 보내고, stdout으로
{pairs:[{a_id,b_id,similarity,longest_fragment,total_overlap,fragments}]}를 받는다.
실패는 예외로 전파 — 표절 검출은 '조용한 빈 결과'로 fail-open 하면 안 되므로 run을 실패로 마감한다.
"""
from __future__ import annotations

import json
import subprocess

from . import config


def run_dolos(files: list[dict], language: str | None = None) -> list[dict]:
    """files: [{"id": str, "content": str}]. 2개 미만이면 비교 불가 → []."""
    if len(files) < 2:
        return []
    payload = json.dumps({"files": files, "language": language or config.LANGUAGE})
    try:
        proc = subprocess.run(
            [config.DOLOS_NODE, config.DOLOS_SCRIPT],
            input=payload,
            capture_output=True,
            text=True,
            timeout=config.DOLOS_TIMEOUT_S,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"Dolos Node 실행 불가 ({config.DOLOS_NODE}): {e}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Dolos timeout({config.DOLOS_TIMEOUT_S}s)") from e
    if proc.returncode != 0:
        raise RuntimeError(f"Dolos 실패(rc={proc.returncode}): {proc.stderr.strip()[:600]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Dolos 출력 파싱 실패: {e}; stdout={proc.stdout[:300]}") from e
    return data.get("pairs", [])

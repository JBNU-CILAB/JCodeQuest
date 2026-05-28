"""순수 Python winnowing 유사도 — Dolos(Node) 사용 불가 시 폴백.

Moss식: 코드를 토큰 정규화(식별자→ID, 숫자→NUM, 문자열→STR; 키워드·연산자·들여쓰기 보존)
→ k-gram 해시 → winnowing 지문 → 지문 Jaccard(Sørensen)로 유사도. 변수명/포맷 변경에 강함.
Dolos만큼 정밀(라인 fragment)하진 않지만 1차 스크리닝엔 충분. 의존성 0(표준 라이브러리만).
"""
from __future__ import annotations

import io
import keyword
import tokenize
import zlib


def _normalize(src: str) -> list[str]:
    out: list[str] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            t, s = tok.type, tok.string
            if t in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                     tokenize.ENCODING, tokenize.ENDMARKER):
                continue
            if t == tokenize.INDENT:
                out.append("§I")
            elif t == tokenize.DEDENT:
                out.append("§D")
            elif t == tokenize.NAME:
                out.append(s if keyword.iskeyword(s) else "ID")
            elif t == tokenize.NUMBER:
                out.append("NUM")
            elif t == tokenize.STRING:
                out.append("STR")
            else:
                out.append(s)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        out = src.split()  # 파싱 실패 시 공백 분할 폴백
    return out


def _kgram_hashes(toks: list[str], k: int) -> list[int]:
    if not toks:
        return []
    if len(toks) < k:
        return [zlib.crc32(" ".join(toks).encode())]
    return [zlib.crc32(" ".join(toks[i:i + k]).encode()) for i in range(len(toks) - k + 1)]


def _winnow(hashes: list[int], w: int) -> set[int]:
    if len(hashes) <= w:
        return set(hashes)
    fps: set[int] = set()
    for i in range(len(hashes) - w + 1):
        fps.add(min(hashes[i:i + w]))
    return fps


def winnow_pairs(files: list[dict], k: int = 5, w: int = 4) -> list[dict]:
    """files: [{"id","content"}] → Dolos와 동일 스키마의 pairs 목록.
    fragments는 비워둔다(라인 정밀 매칭은 Dolos 전용)."""
    norm = {f["id"]: _normalize(f["content"]) for f in files}
    kg = {fid: _kgram_hashes(t, k) for fid, t in norm.items()}
    fp = {fid: _winnow(h, w) for fid, h in kg.items()}
    hset = {fid: set(h) for fid, h in kg.items()}
    ids = list(norm)
    pairs: list[dict] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            fa, fb = fp[a], fp[b]
            if not fa or not fb:
                continue
            shared = fa & fb
            sim = 2 * len(shared) / (len(fa) + len(fb))
            # a의 k-gram 중 b에도 있는 해시의 최장 연속 길이 ≈ 최장 매칭 구간
            longest = cur = 0
            hb = hset[b]
            for h in kg[a]:
                if h in hb:
                    cur += 1
                    longest = max(longest, cur)
                else:
                    cur = 0
            pairs.append({
                "a_id": a, "b_id": b,
                "similarity": round(sim, 4),
                "longest_fragment": longest,
                "total_overlap": len(shared),
                "fragments": [],
            })
    return pairs

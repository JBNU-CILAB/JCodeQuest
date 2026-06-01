"""JCodeQuest 표절 검토 엔진.

Dolos(구조 유사도)로 의심 쌍을 뽑고(Phase 1), 이후 멀티에이전트 판정(Phase 2)을 얹어
admin '표절 검토' 큐로 올린다. DB는 backend가 단일 소유 — 모든 읽기/쓰기는 /internal/* 위임.
"""

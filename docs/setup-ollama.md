# A6000 서버 부트스트랩 메모

## 0. 사전 점검

```bash
nvidia-smi                          # A6000(48GB) 인식 + 드라이버 ≥ 535
nvcc --version || true              # 옵션 — 모델 추론엔 불필요
free -h && df -h                    # RAM 32GB+, /var 50GB+ 권장
python3 --version                   # 3.11+
```

## 1. Ollama 설치

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl status ollama        # active(running) 확인
```

기본 11434 포트로 뜸. 외부 노출하려면 `Environment="OLLAMA_HOST=0.0.0.0"`을 systemd unit에 추가.

## 2. Ollama 환경변수 (systemd override)

```bash
sudo systemctl edit ollama
```

```ini
[Service]
Environment="OLLAMA_MAX_LOADED_MODELS=4"
Environment="OLLAMA_NUM_PARALLEL=2"
Environment="OLLAMA_KEEP_ALIVE=24h"
Environment="OLLAMA_FLASH_ATTENTION=1"
```

- `MAX_LOADED_MODELS=4`: 주심1 + 부심2 + 임베딩 동시 상주
- `NUM_PARALLEL=2`: 모델당 KV 캐시 2벌 — 워커 동시 호출 대비
- `KEEP_ALIVE=24h`: 모델 unload 방지 (콜드스타트 0)
- `FLASH_ATTENTION=1`: A6000 Ampere에서 ~20% 속도 ↑

```bash
sudo systemctl restart ollama
```

## 3. 모델 풀

코드 기본값(`judge_engine/judge/ensemble.py`, `authoring/config.py`)과 일치하는 태그를 받는다:

```bash
ollama pull qwen2.5-coder:14b-instruct-q5_K_M    # Melchior(주심) + 출제 생성 (~10GB)
ollama pull deepseek-coder-v2:lite               # Balthasar(부심1, MoE)
ollama pull llama3.1:8b                          # Casper(부심2 / 의도 분석)
ollama pull bge-m3                               # 임베딩 (novelty + RAG, 1024차원)
```

- 모델 태그는 환경변수로 덮어쓸 수 있다: `JCQ_ENSEMBLE_MODEL_{MELCHIOR,BALTHASAR,CASPER}`, 임베딩은 `JCQ_EMBED_MODEL`(기본 `bge-m3`). judge_engine·authoring_engine이 **같은 `JCQ_ENSEMBLE_MODEL_*`를 공유**한다.
- 임베딩 모델은 출제 엔진의 novelty 검사(중복 회피)와 RAG exemplar 검색에 쓰인다 — `bge-m3`를 pull하지 않으면 두 기능 모두 fail-open으로 무력화된다.

총 VRAM 점유 ~28GB / 48GB (모델 quant에 따라 변동).

## 4. 스모크 테스트

```bash
# JSON mode + 한국어 출력 — 각 모델별
for m in qwen2.5-coder:14b-instruct-q5_K_M \
         deepseek-coder-v2:lite \
         llama3.1:8b; do
  echo "=== $m ==="
  time curl -s http://localhost:11434/api/chat \
    -d "{\"model\":\"$m\",
         \"messages\":[{\"role\":\"user\",
                        \"content\":\"코드 채점관입니다. AC인지 SUS인지 JSON으로만: print('hi')\"}],
         \"format\":\"json\",
         \"options\":{\"temperature\":0},
         \"stream\":false}" | jq .message.content
done
```

목표 latency: 14B ≤ 5s, 16B-MoE ≤ 3s, 8B ≤ 2s. 14B가 8s를 넘으면 `q4_K_M`으로 한 단계 낮추기.

```bash
nvidia-smi                          # ~28GB 점유 확인
```

## 5. 채점 엔진 셋업

> 채점 큐·샌드박스·3-judge 앙상블은 모두 **judge_engine**으로 분리됐다. GPU 박스에는 보통 Ollama + judge_engine(+필요 시 authoring_engine)을 띄운다. backend는 Supabase Postgres를 쓰므로 이 박스에 DB 파일을 둘 필요가 없다.

```bash
git clone <repo> jcodequest && cd jcodequest/judge_engine
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 6. 환경변수

judge_engine은 `judge_engine/.env`를 `python-dotenv`로 자동 로드한다(`source` 불필요):

```bash
# judge_engine/.env
OLLAMA_BASE_URL=http://localhost:11434
JCQ_BACKEND_URL=http://<backend-host>:8000        # webhook 회신 대상
JCQ_INTERNAL_SECRET=change-me-shared-with-backend  # backend·authoring과 동일 값
JCQ_QUEUE_CONCURRENCY=1                            # 1로 시작, 안정 후 2~3
# 모델 태그 덮어쓰기(선택, 기본값은 코드와 동일)
# JCQ_ENSEMBLE_MODEL_MELCHIOR=qwen2.5-coder:14b-instruct-q5_K_M
# JCQ_ENSEMBLE_MODEL_BALTHASAR=deepseek-coder-v2:lite
# JCQ_ENSEMBLE_MODEL_CASPER=llama3.1:8b
# JCQ_SKIP_ENSEMBLE=1                              # Ollama 없이 stub AC (개발용)
```

(authoring_engine까지 같은 박스에 띄운다면 `JCQ_EMBED_MODEL`·`JCQ_ADMIN_TOKEN` 등은 `docs/authoring-engine.md` §3 참조.)

## 7. 실행

```bash
# 개발
.venv/bin/uvicorn judge.server:app --host 0.0.0.0 --port 8002 --reload

# 프로덕션 (단일 워커 — 큐가 인-프로세스라 멀티 워커 금지)
.venv/bin/uvicorn judge.server:app --host 0.0.0.0 --port 8002
```

`--workers N`을 쓰면 안 됨 — JobQueue(`judge/queue.py`)가 프로세스마다 따로 떠서 잡 분배가 깨짐. 수평확장이 필요해지면 그때 Redis 기반으로 갈아엎기.

## 8. 헬스체크

```bash
curl http://localhost:8002/api/health     # judge_engine
# {"status":"ok"}
```

## 9. 테스트 실행

judge_engine의 샌드박스/큐 단위 테스트:

```bash
cd judge_engine && .venv/bin/pytest    # test_sandbox.py, test_jobqueue.py
```

3-judge 앙상블의 라이브 LLM 슈트는 **backend** 쪽에 있다(`backend/tests/live/`). Ollama 없이도 일반 pytest는 LLM monkeypatch로 통과.

### 9.1 라이브 LLM 슈트 (`backend/tests/live/`)

3-judge ensemble을 실 Ollama에 직접 꽂아서 시나리오별 채점 결과 + 각 판사 의견을 디스크에 통째로 기록한다. 옵트인:

```bash
cd backend && source env.sh         # OLLAMA_BASE_URL 등 주입
JCQ_RUN_LIVE_LLM=1 .venv/bin/pytest tests/live -v -s
```

플래그가 없거나 Ollama가 닫혀있으면 `tests/live/`는 통째로 skip. 기록물은 `tests/artifacts/`에:

- `live_llm_<ts>.jsonl` — 시나리오별 raw 레코드 (테스트 실행 중 즉시 flush, 중간 죽어도 살아있음)
- `live_llm_<ts>.md` — 사람이 읽는 요약 표 + 각 판사의 verdict / rationale 상세

시나리오 셋:
- AC 정석 (factorial 누적 곱) / 재귀 / trivial(n*2) — ensemble이 안정적으로 AC 합의하는지
- SUS 하드코딩 (if/elif로 정답 매핑) — rubric의 forbidden_pattern을 LLM이 잡아내는지
- WA / RE / TLE — 샌드박스 단계에서 SUS 확정, LLM 미호출 경로 검증

LLM 응답은 비결정적이라 expected_verdict와 actual이 어긋나면 테스트는 fail 처리되지만, 그 자체가 분석 신호 — markdown에 `UNEXPECTED` 라벨로 따로 보임.

## 10. systemd 서비스 (옵션)

```ini
# /etc/systemd/system/jcq-judge.service
[Unit]
Description=JCodeQuest judge_engine
After=network.target ollama.service
Requires=ollama.service

[Service]
User=jcq
WorkingDirectory=/srv/jcodequest/judge_engine
EnvironmentFile=/etc/jcq-judge.env
ExecStart=/srv/jcodequest/judge_engine/.venv/bin/uvicorn judge.server:app --host 0.0.0.0 --port 8002
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now jcq-judge
```

## 함정 모음

- `OLLAMA_KEEP_ALIVE`를 짧게 두면 첫 요청마다 14B 로딩에 30s+ 걸림. 24h 박을 것.
- 첫 ensemble 호출은 모델 3개 cold start로 분 단위 걸릴 수 있음. 부팅 직후 워밍업 호출 1번씩 미리 때리기.
- 샌드박스는 **순수 Python 격리**(`judge/sandbox/runner.py`) — import 차단 + RLIMIT. RLIMIT은 Unix 한정이라 Mac은 일부 동작, Windows는 불가. 프로덕션은 Linux 컨테이너에서.
- judge_engine은 DB를 직접 보지 않는다 — 채점 결과는 webhook(`/internal/grade-events`)으로 backend에 회신한다. `JCQ_INTERNAL_SECRET`이 backend와 다르면 401로 막힌다.
- uvicorn `--workers`는 절대 쓰지 말 것 (위 7번 참조).

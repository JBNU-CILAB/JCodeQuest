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

```bash
ollama pull qwen2.5-coder:14b-instruct-q5_K_M    # 주심 + 출제 생성 (~10GB)
ollama pull deepseek-coder-v2:16b-lite-instruct  # 부심1 (~10GB, MoE)
ollama pull llama3.1:8b-instruct-q5_K_M          # 부심2 / 의도 분석 (~6GB)
ollama pull nomic-embed-text                     # 임베딩 (~1.5GB, 옵션)
```

총 VRAM 점유 ~28GB / 48GB.

## 4. 스모크 테스트

```bash
# JSON mode + 한국어 출력 — 각 모델별
for m in qwen2.5-coder:14b-instruct-q5_K_M \
         deepseek-coder-v2:16b-lite-instruct \
         llama3.1:8b-instruct-q5_K_M; do
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

## 5. 백엔드 셋업

```bash
git clone <repo> jcodequest && cd jcodequest/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 6. 환경변수

```bash
# .env 또는 systemd override
export OLLAMA_BASE_URL=http://localhost:11434
export JCQ_DB_URL=sqlite:////var/lib/jcq/jcq.db   # 절대경로 권장
export JCQ_QUEUE_CONCURRENCY=1                    # 1로 시작, 안정 후 2~3
```

DB 파일 디렉토리 미리 생성:
```bash
sudo mkdir -p /var/lib/jcq && sudo chown $USER /var/lib/jcq
```

## 7. 실행

```bash
# 개발
.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# 프로덕션 (단일 워커 — 큐가 인-프로세스라 멀티 워커 금지)
.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000
```

`--workers N`을 쓰면 안 됨 — JobQueue가 프로세스마다 따로 떠서 잡 분배가 깨짐. 수평확장이 필요해지면 그때 Redis 기반으로 갈아엎기 (history.md 참조).

## 8. 헬스체크

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## 9. 테스트 실행

```bash
.venv/bin/pytest                    # Ollama 없이도 통과 (LLM monkeypatch)
```

실 Ollama 통합 테스트는 별도 — `OLLAMA_BASE_URL` 띄워둔 채 `tests/test_pipeline.py`에서 monkeypatch 빼고 돌리면 됨.

## 10. systemd 서비스 (옵션)

```ini
# /etc/systemd/system/jcq.service
[Unit]
Description=JCodeQuest backend
After=network.target ollama.service
Requires=ollama.service

[Service]
User=jcq
WorkingDirectory=/srv/jcodequest/backend
EnvironmentFile=/etc/jcq.env
ExecStart=/srv/jcodequest/backend/.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now jcq
```

## 함정 모음

- `OLLAMA_KEEP_ALIVE`를 짧게 두면 첫 요청마다 14B 로딩에 30s+ 걸림. 24h 박을 것.
- 첫 ensemble 호출은 모델 3개 cold start로 분 단위 걸릴 수 있음. 부팅 직후 워밍업 호출 1번씩 미리 때리기.
- SQLite WAL은 자동으로 켜지지만 (`storage/db.py`), DB 파일을 NFS에 두면 락이 깨짐. 로컬 디스크 필수.
- subprocess sandbox는 Linux 한정. Mac에서 일부 동작, Windows 불가. 프로덕션은 Linux 컨테이너에서.
- uvicorn `--workers`는 절대 쓰지 말 것 (위 7번 참조).

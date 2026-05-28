"""임시 스모크: GET /users/{id} 익명/비익명 마스킹 검증. 실행 후 삭제."""
import os
import tempfile
from pathlib import Path

_db_fd, _db_path = tempfile.mkstemp(prefix="jcq_smoke_", suffix=".db")
os.close(_db_fd)
os.environ["JCQ_DB_URL"] = f"sqlite:///{_db_path}"
os.environ["JCQ_ALLOW_NON_POSTGRES"] = "1"
os.environ.setdefault("JCQ_SKIP_ENSEMBLE", "1")

from fastapi.testclient import TestClient  # noqa: E402

from src.main import app  # noqa: E402
from src.storage import get_session, init_db  # noqa: E402
from src.storage.models import SubmissionRow  # noqa: E402
from src.storage.users import get_or_create_user  # noqa: E402

init_db()

with get_session() as s:
    pub = get_or_create_user(
        s, provider="dev_stub", external_id="pub1", display_name="공개유저"
    )
    pub.exp = 500
    pub.tier = "silver"
    pub.grade = 3
    pub.department = "컴퓨터공학부"
    pub.nickname = "pubnick"
    s.add(pub)

    anon = get_or_create_user(
        s, provider="dev_stub", external_id="anon1", display_name="실명숨김"
    )
    anon.exp = 800
    anon.tier = "gold"
    anon.grade = 4
    anon.department = "전자공학부"
    anon.nickname = "익명닉"
    anon.is_anonymous = True
    s.add(anon)
    s.commit()
    s.refresh(pub)
    s.refresh(anon)
    pub_id, anon_id = pub.id, anon.id
    # 공개유저에게 AC 제출 2건(서로 다른 문제) — solved/total 검증용
    s.add(SubmissionRow(user_id=pub_id, problem_id=1, code="x", final_verdict="AC"))
    s.add(SubmissionRow(user_id=pub_id, problem_id=2, code="x", final_verdict="AC"))
    s.add(SubmissionRow(user_id=pub_id, problem_id=2, code="x", final_verdict="SUS"))
    s.commit()

client = TestClient(app)

r_pub = client.get(f"/users/{pub_id}")
r_anon = client.get(f"/users/{anon_id}")
r_404 = client.get("/users/999999")

print("=== 비익명 ===", r_pub.status_code)
print(r_pub.json())
print("=== 익명 ===", r_anon.status_code)
print(r_anon.json())
print("=== 404 ===", r_404.status_code)

pub_body = r_pub.json()
anon_body = r_anon.json()

assert r_pub.status_code == 200
assert r_pub.json()["display_name"] == "공개유저"
assert pub_body["grade"] == 3 and pub_body["department"] == "컴퓨터공학부"
assert pub_body["stats"]["solved"] == 2
assert pub_body["stats"]["total_submissions"] == 3
assert pub_body["is_anonymous"] is False

assert r_anon.status_code == 200
assert anon_body["display_name"] == "익명닉"  # nickname 으로 마스킹
assert anon_body["is_anonymous"] is True
# 익명: 신원 단서/통계는 전부 None 이어야 함
assert anon_body["avatar_url"] is None
assert anon_body["grade"] is None
assert anon_body["department"] is None
assert anon_body["stats"] is None
assert anon_body["rank"] is None
# 응답에 실명/이메일이 새지 않아야 함
assert "실명숨김" not in r_anon.text
assert "email" not in anon_body

assert r_404.status_code == 404

print("\nALL ASSERTIONS PASSED")

try:
    os.unlink(_db_path)
except OSError:
    pass

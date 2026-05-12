"""인증된 본인 프로필. 추후 /me/submissions, /me/stats 등이 같은 라우터에 붙는다."""
from fastapi import APIRouter, Depends

from ..auth.deps import get_current_user
from ..storage.models import UserRow

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
def me(user: UserRow = Depends(get_current_user)) -> dict:
    return {
        "id": user.id,
        "display_name": user.display_name,
        "email": user.email,
        "provider": user.provider,
        "exp": user.exp,
        "tier": user.tier,
    }

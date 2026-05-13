"""Supabase JWT 검증."""
import os

import jwt


def verify_supabase_jwt(token: str) -> dict:
    secret = os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        raise RuntimeError("SUPABASE_JWT_SECRET not set")
    return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")

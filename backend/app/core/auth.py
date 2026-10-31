from dataclasses import dataclass
from uuid import UUID
from fastapi import Depends, Header, HTTPException
from app.integrations.supabase import SupabaseGateway, get_gateway


@dataclass(frozen=True)
class Principal:
    id: UUID
    role: str
    token: str


async def current_user(authorization: str | None = Header(default=None), gateway: SupabaseGateway = Depends(get_gateway)) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required.")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Authentication required.")
    user = await gateway.user(token)
    try:
        user_id = UUID(user["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(401, "Invalid identity.") from exc
    rows = await gateway.table("profiles", token=token, params={"select": "id,role", "id": f"eq.{user_id}", "limit": 1})
    if not isinstance(rows, list) or not rows:
        raise HTTPException(403, "Profile is not ready.")
    role = rows[0].get("role")
    if role not in {"citizen", "authority", "admin"}:
        raise HTTPException(403, "Invalid role.")
    return Principal(id=user_id, role=role, token=token)


def require_roles(*roles: str):
    async def dependency(user: Principal = Depends(current_user)) -> Principal:
        if user.role not in roles:
            raise HTTPException(403, "Insufficient role.")
        return user
    return dependency

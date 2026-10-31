from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import Principal, current_user, require_roles
from app.integrations.supabase import SupabaseGateway, get_gateway
from app.repositories.supabase import Repository
from app.schemas.profile import Profile, ProfileUpdate, RoleAssignment

router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=Profile)
async def get_profile(user: Principal = Depends(current_user), gateway: SupabaseGateway = Depends(get_gateway)):
    row = await Repository(gateway, user.token).one("profiles", user.id)
    if row is None:
        raise HTTPException(404, "Profile not found.")
    return Profile.model_validate(row)


@router.patch("/profile", response_model=Profile)
async def update_profile(body: ProfileUpdate, user: Principal = Depends(current_user), gateway: SupabaseGateway = Depends(get_gateway)):
    row = await Repository(gateway, user.token).update("profiles", user.id, body.model_dump())
    if row is None:
        raise HTTPException(404, "Profile not found.")
    return Profile.model_validate(row)


@router.patch("/profiles/{profile_id}/role", response_model=Profile)
async def assign_role(profile_id: UUID, body: RoleAssignment, admin: Principal = Depends(require_roles("admin")), gateway: SupabaseGateway = Depends(get_gateway)):
    if profile_id == admin.id and body.role != "admin":
        raise HTTPException(400, "Use another admin to change your own admin role.")
    row = await Repository(gateway).update("profiles", profile_id, {"role": body.role.value}, privileged=True)
    if row is None:
        raise HTTPException(404, "Profile not found.")
    await gateway.table("audit_logs", "POST", privileged=True, json={"actor_id": str(admin.id), "action": "profile.role_changed", "entity_type": "profile", "entity_id": str(profile_id), "details": {"role": body.role.value}})
    return Profile.model_validate(row)


@router.get("/profiles", response_model=list[Profile])
async def list_profiles(admin: Principal = Depends(require_roles("admin")), gateway: SupabaseGateway = Depends(get_gateway)):
    rows = await Repository(gateway).gateway.table("profiles", privileged=True, params={"select": "id,display_name,role,created_at,updated_at", "order": "created_at.desc", "limit": 200})
    return [Profile.model_validate(row) for row in rows] if isinstance(rows, list) else []

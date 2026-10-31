from uuid import UUID
from app.integrations.supabase import SupabaseGateway


class Repository:
    def __init__(self, gateway: SupabaseGateway, token: str | None = None):
        self.gateway = gateway
        self.token = token

    async def list(self, table: str, select: str, *, filters: dict[str, str] | None = None, limit: int = 100, order: str | None = None) -> list[dict]:
        params = {"select": select, "limit": min(limit, 200), **(filters or {})}
        if order:
            params["order"] = order
        rows = await self.gateway.table(table, token=self.token, params=params)
        return rows if isinstance(rows, list) else []

    async def one(self, table: str, row_id: UUID | str, select: str = "*") -> dict | None:
        rows = await self.list(table, select, filters={"id": f"eq.{row_id}"}, limit=1)
        return rows[0] if rows else None

    async def insert(self, table: str, payload: dict) -> dict:
        rows = await self.gateway.table(table, "POST", token=self.token, json=payload, prefer="return=representation")
        return rows[0] if isinstance(rows, list) and rows else {}

    async def update(self, table: str, row_id: UUID | str, payload: dict, *, privileged: bool = False) -> dict | None:
        rows = await self.gateway.table(table, "PATCH", token=self.token, privileged=privileged, params={"id": f"eq.{row_id}"}, json=payload, prefer="return=representation")
        return rows[0] if isinstance(rows, list) and rows else None

    async def delete(self, table: str, row_id: UUID | str) -> None:
        await self.gateway.table(table, "DELETE", token=self.token, params={"id": f"eq.{row_id}"})

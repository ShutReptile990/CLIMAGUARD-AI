"""Small read-only compatibility probe while migration 008 is pending."""

from app.core.errors import UpstreamError
from app.integrations.supabase import SupabaseGateway


async def workflow_columns_ready(gateway: SupabaseGateway, table: str, column: str, token: str) -> bool:
    try:
        await gateway.table(table, token=token, params={"select": column, "limit": 0})
        return True
    except UpstreamError:
        return False

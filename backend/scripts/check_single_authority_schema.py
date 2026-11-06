"""Read-only marker check for migration 010; does not prove trigger behavior."""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.core.errors import UpstreamError
from app.integrations.supabase import SupabaseGateway


async def main() -> None:
    gateway = SupabaseGateway(get_settings())
    try:
        try:
            await gateway.table("alerts", privileged=True, params={"select": "incident_id", "limit": 0})
        except UpstreamError:
            print("migration_010_column: unavailable")
        else:
            print("migration_010_column: available; verify approval trigger with an authenticated TEST draft")
    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())

"""Read-only inventory of explicitly labeled TEST incidents and their review audit rows."""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.integrations.supabase import SupabaseGateway


async def main() -> None:
    gateway = SupabaseGateway(get_settings())
    try:
        rows = await gateway.table("incident_reports", privileged=True,
            params={"select": "id,status,description,reviewed_by,reviewed_at", "order": "created_at.desc", "limit": 100})
        print("incident_count_sample:", len(rows))
        for row in rows:
            is_test = row["description"].lstrip().upper().startswith("TEST")
            if not is_test:
                continue
            logs = await gateway.table("audit_logs", privileged=True,
                params={"select": "actor_id,details", "entity_type": "eq.incident_reports",
                        "entity_id": f"eq.{row['id']}", "limit": 100})
            reviewer = await gateway.table("profiles", privileged=True,
                params={"select": "role", "id": f"eq.{row['reviewed_by']}", "limit": 1}) if row.get("reviewed_by") else []
            print("test_incident:", row["id"], "status:", row["status"],
                  "reviewer_recorded:", bool(row.get("reviewed_by")),
                  "reviewer_role:", reviewer[0]["role"] if reviewer else "unavailable",
                  "reviewed_at_recorded:", bool(row.get("reviewed_at")),
                  "status_audit_entries:", len(logs),
                  "transitions:", [(log.get("details") or {}).get("old_status", "unknown") + "->" +
                                   (log.get("details") or {}).get("new_status", "unknown") for log in logs])
    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())

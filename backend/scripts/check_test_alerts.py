"""Read-only inventory of explicitly TEST-labeled official alerts.

Prints status and approval metadata only, never alert body or account identity.
"""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.integrations.supabase import SupabaseGateway


async def main() -> None:
    gateway = SupabaseGateway(get_settings())
    try:
        rows = await gateway.table("alerts", privileged=True,
            params={"select": "id,title,status,locality_id,created_by,approved_by,submitted_at,reviewed_at,published_at,expires_at", "order": "created_at.desc", "limit": 100})
        print("alert_count_sample:", len(rows))
        print("status_counts:", {status: sum(row["status"] == status for row in rows)
                                 for status in sorted({row["status"] for row in rows})})
        for row in rows:
            if not row["title"].lstrip().upper().startswith("TEST"):
                continue
            logs = await gateway.table("audit_logs", privileged=True,
                params={"select": "actor_id,action,details", "entity_type": "eq.alerts",
                        "entity_id": f"eq.{row['id']}", "order": "created_at.asc", "limit": 100})
            print("test_alert:", row["id"], "status:", row["status"], "cell:", row["locality_id"],
                  "submitted:", bool(row.get("submitted_at")),
                  "reviewed:", bool(row.get("reviewed_at")),
                  "approval_by_author:", bool(row.get("approved_by") and row["approved_by"] == row["created_by"]),
                  "published:", bool(row.get("published_at")),
                  "expires:", bool(row.get("expires_at")),
                  "audit_count:", len(logs),
                  "audit_actions:", [log["action"] for log in logs],
                  "audit_actors_match_author:", all(log.get("actor_id") == row["created_by"] for log in logs))
    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())

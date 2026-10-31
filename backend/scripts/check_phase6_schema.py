"""Read-only check for migration 008; never prints credentials or records."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.integrations.supabase import SupabaseGateway


async def main() -> None:
    gateway = SupabaseGateway(get_settings())
    try:
        for table, fields in (("incident_reports", "severity,image_path,reviewed_at"),
                              ("alerts", "hazard,submitted_at,reviewed_at,published_at,expires_at")):
            try:
                await gateway.table(table, privileged=True, params={"select": fields, "limit": 0})
                print(f"{table}: migration 008 columns available")
            except Exception:
                print(f"{table}: migration 008 columns unavailable")
        try:
            rows = await gateway.table("profiles", privileged=True, params={"select": "role", "limit": 200})
            print("role_counts_first_200:", {role: sum(row.get("role") == role for row in rows or [])
                                             for role in ("citizen", "authority", "admin")})
        except Exception:
            print("role_counts: unavailable")
        try:
            logs = await gateway.table("audit_logs", privileged=True,
                params={"select": "action,details", "action": "eq.profile.role_changed", "order": "created_at.desc", "limit": 200})
            print("audited_server_authority_assignments:", sum(
                row.get("details", {}).get("method") == "server_side_assignment"
                and row.get("details", {}).get("role") == "authority" for row in logs or []))
        except Exception:
            print("authority_assignment_audit: unavailable")
        try:
            bucket = await gateway.request("GET", "/storage/v1/bucket/incident-evidence", privileged=True)
            print("incident-evidence bucket:", "private" if bucket.get("public") is False else "unexpected visibility")
        except Exception:
            print("incident-evidence bucket: unavailable")
        try:
            await gateway.table("alerts", params={"select": "id", "status": "eq.published",
                "or": f"(expires_at.is.null,expires_at.gt.{datetime.now(timezone.utc).isoformat()})", "limit": 1})
            print("public active-alert expiry filter: available")
        except Exception:
            print("public active-alert expiry filter: unavailable")
    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())

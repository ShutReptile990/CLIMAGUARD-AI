"""Read-only live check of the public alert API; prints counts and statuses only."""

import asyncio
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app


async def main() -> None:
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for locality in (None, "pune-grid-r2-c2"):
                params = {"locality_id": locality} if locality else None
                response = await client.get("/api/v1/alerts", params=params)
                print("scope:", locality or "all Pune cells", "http_status:", response.status_code)
                if response.is_success:
                    rows = response.json()
                    print("active_count:", len(rows), "statuses:", sorted({row["status"] for row in rows}),
                          "cells:", sorted({row["localityId"] for row in rows}))
                    if locality is None:
                        for row in rows:
                            logs = await app.state.supabase.table("audit_logs", privileged=True,
                                params={"select": "actor_id,action,details", "entity_type": "eq.alerts",
                                        "entity_id": f"eq.{row['id']}", "order": "created_at.asc", "limit": 100})
                            publication = [entry for entry in logs or []
                                           if (entry.get("details") or {}).get("new_status") == "published"]
                            actor = publication[-1].get("actor_id") if publication else None
                            print("public_alert_metadata:", "test_labeled:", row["title"].lstrip().upper().startswith("TEST"),
                                  "published_audit_entries:", len(publication),
                                  "publisher_matches_approver:", bool(actor and actor == row.get("approvedBy")),
                                  "publisher_matches_author:", bool(actor and actor == row.get("createdBy")))
                else:
                    print("error_type:", response.json().get("detail", "unknown"))


if __name__ == "__main__":
    asyncio.run(main())

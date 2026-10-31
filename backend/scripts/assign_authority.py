"""Assign named, confirmed Auth users the authority role using server-side credentials.

Dry run by default. Never stores emails or credentials in source files.
"""

import argparse
import asyncio
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.integrations.supabase import SupabaseGateway


async def auth_users(gateway: SupabaseGateway) -> list[dict]:
    users: list[dict] = []
    page = 1
    while True:
        result = await gateway.request("GET", "/auth/v1/admin/users", privileged=True,
                                       params={"page": page, "per_page": 200})
        batch = result.get("users", []) if isinstance(result, dict) else []
        users.extend(batch)
        if len(batch) < 200:
            return users
        page += 1
        if page > 50:
            raise RuntimeError("Auth user listing exceeds the safety limit")


async def main(emails: list[str], apply: bool) -> None:
    if not 1 <= len(emails) <= 2 or len({email.casefold() for email in emails}) != len(emails):
        raise SystemExit("Provide one or two distinct existing Auth account emails.")
    settings = get_settings()
    if not settings.supabase_secret_key:
        raise SystemExit("Server-side Supabase secret key is required.")
    gateway = SupabaseGateway(settings)
    try:
        all_users = await auth_users(gateway)
        targets = []
        for index, email in enumerate(emails, 1):
            matches = [user for user in all_users if (user.get("email") or "").casefold() == email.casefold()]
            if len(matches) != 1:
                print(f"target_{index}: exact Auth account unavailable")
                raise SystemExit(2)
            user = matches[0]
            print(f"target_{index}: invite_marker={bool(user.get('invited_at'))} "
                  f"confirmed_marker={bool(user.get('confirmed_at'))} "
                  f"last_sign_in_marker={bool(user.get('last_sign_in_at'))}")
            invited_at = user.get("invited_at")
            signed_in_at = user.get("last_sign_in_at")
            if invited_at and signed_in_at:
                accepted_after_invite = datetime.fromisoformat(signed_in_at.replace("Z", "+00:00")) > datetime.fromisoformat(invited_at.replace("Z", "+00:00"))
                print(f"target_{index}: signed_in_after_invite={accepted_after_invite}")
            else:
                accepted_after_invite = False
            if invited_at and not accepted_after_invite:
                print(f"target_{index}: invitation not yet accepted; no role change")
                raise SystemExit(2)
            if not user.get("email_confirmed_at"):
                print(f"target_{index}: email confirmation pending")
                raise SystemExit(2)
            rows = await gateway.table("profiles", privileged=True,
                params={"select": "id,role", "id": f"eq.{user['id']}", "limit": 1})
            if not isinstance(rows, list) or len(rows) != 1:
                print(f"target_{index}: profile unavailable")
                raise SystemExit(2)
            print(f"target_{index}: confirmed Auth user, profile role={rows[0]['role']}")
            targets.append(rows[0])
        if any(row["role"] != "citizen" for row in targets):
            print("No changes: each target profile must currently have the citizen role.")
            raise SystemExit(2)
        if not apply:
            print("Dry run only; no role changed. Pass --apply after reviewing both targets.")
            return
        for index, row in enumerate(targets, 1):
            changed = await gateway.table("profiles", "PATCH", privileged=True,
                params={"id": f"eq.{row['id']}", "role": "eq.citizen"},
                json={"role": "authority"}, prefer="return=representation")
            if not isinstance(changed, list) or len(changed) != 1:
                raise RuntimeError(f"target_{index}: role changed concurrently; stop and inspect")
            await gateway.table("audit_logs", "POST", privileged=True,
                json={"actor_id": None, "action": "profile.role_changed", "entity_type": "profile",
                      "entity_id": row["id"], "details": {"role": "authority", "method": "server_side_assignment",
                                                     "purpose": "Phase 6 two-person authority test"}},
                prefer="return=minimal")
            print(f"target_{index}: authority role assigned and audit record stored")
    finally:
        await gateway.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", action="append", required=True, help="Exact existing confirmed Auth user email; supply once or twice")
    parser.add_argument("--apply", action="store_true", help="Perform audited role updates after dry-run verification")
    args = parser.parse_args()
    asyncio.run(main(args.email, args.apply))

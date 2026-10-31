"""Invite one named Auth user; authority role is assigned only after confirmation."""

import argparse
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.integrations.supabase import SupabaseGateway
from scripts.assign_authority import auth_users


async def main(email: str, redirect_to: str) -> None:
    gateway = SupabaseGateway(get_settings())
    try:
        existing = await auth_users(gateway)
        if any((user.get("email") or "").casefold() == email.casefold() for user in existing):
            raise SystemExit("Exact Auth account already exists; no invitation sent.")
        result = await gateway.request("POST", "/auth/v1/invite", privileged=True,
            params={"redirect_to": redirect_to}, json={"email": email})
        user_id = result.get("id") if isinstance(result, dict) else None
        if not user_id:
            raise RuntimeError("Supabase did not return an invited user ID")
        print("Supabase Auth accepted the invitation request; await recipient confirmation.")
    finally:
        await gateway.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Exact invitation recipient")
    parser.add_argument("--redirect-to", default="http://127.0.0.1:5173/reset-password")
    args = parser.parse_args()
    asyncio.run(main(args.email, args.redirect_to))

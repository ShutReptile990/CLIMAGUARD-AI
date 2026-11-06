"""Exercise real Open-Meteo + Nugen inference through the FastAPI route."""

import asyncio
import json
from pathlib import Path
import sys
import httpx
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app


async def main() -> None:
    zone = sys.argv[1] if len(sys.argv) > 1 else "pune-grid-r2-c2"
    if zone != "pune" and not re.fullmatch(r"pune-grid-r[1-3]-c[1-3]", zone):
        raise SystemExit("Expected Pune overview or a Pune analysis grid cell slug.")
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=150) as client:
            status = await client.get("/api/nugen/status")
            response = await client.post(f"/api/nugen/citizen/{zone}")
            payload = response.json()
            print(json.dumps({"zone": zone, "status_http": status.status_code, "configured": status.json().get("configured"),
                              "guidance_http": response.status_code, "guidance_status": payload.get("status"),
                              "model_id_present": bool(payload.get("model_id")),
                              "provider_request_id_present": bool(payload.get("provider_request_id")),
                              "actions": len(payload.get("guidance", {}).get("actions", [])),
                              "source_hazards": [item.get("hazard") for item in payload.get("source_analysis", {}).get("hazards", [])],
                              "persistence": payload.get("persistence"), "detail": payload.get("detail")}, default=str))
            if status.status_code != 200 or response.status_code != 200:
                raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

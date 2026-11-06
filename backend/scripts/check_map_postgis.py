"""Exercise public FastAPI map endpoints without printing mapped locations."""

import asyncio
import json
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app


async def main() -> None:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=90) as client:
            output = {}
            for kind in ("infrastructure", "roads"):
                response = await client.get(f"/api/v1/map/{kind}")
                data = response.json()
                output[kind] = {"http_status": response.status_code, "storage": data.get("storage"),
                                "status": data.get("status"), "returned_count": data.get("returned_count"),
                                "total_count": data.get("total_count"), "truncated": data.get("truncated"),
                                "counts": data.get("counts")}
                if response.status_code != 200 or data.get("storage") != "postgis":
                    raise SystemExit(json.dumps(output))
            empty = await client.get("/api/v1/map/infrastructure", params={"bbox": "73.5,18.2,73.51,18.21"})
            empty_data = empty.json()
            output["empty_viewport"] = {"http_status": empty.status_code, "storage": empty_data.get("storage"),
                                        "returned_count": empty_data.get("returned_count")}
            if empty.status_code != 200 or empty_data.get("storage") != "postgis" or empty_data.get("returned_count") != 0:
                raise SystemExit(json.dumps(output))
            print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

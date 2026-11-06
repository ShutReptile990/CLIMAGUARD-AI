"""Run one real live and one real simulation guidance request through FastAPI.

Prints status and provenance only, never credentials or generated advice.
"""

import asyncio
import json
from pathlib import Path
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app


async def main() -> None:
    output = {}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=120) as client:
            for name, body in (('live', {'mode': 'live'}),
                               ('simulation', {'mode': 'simulation', 'scenario_id': 'extreme_rainfall'})):
                response = await client.post('/api/v1/nugen/citizen/pune-grid-r2-c2', json=body)
                payload = response.json()
                output[name] = {
                    'http_status': response.status_code,
                    'mode': payload.get('mode'),
                    'scenario_id': payload.get('scenario_id'),
                    'model_id_matches_config': payload.get('model_id') == app.state.nugen.settings.nugen_model_id,
                    'provider_request_id_present': bool(payload.get('provider_request_id')),
                    'action_count': len(payload.get('guidance', {}).get('actions', [])),
                    'persistence': payload.get('persistence'),
                    'hazards': {item['hazard']: item['level'] for item in payload.get('source_analysis', {}).get('hazards', [])},
                    'error_code': payload.get('error', {}).get('code') if isinstance(payload.get('error'), dict) else None,
                }
            print(json.dumps(output, indent=2))
            if any(item['http_status'] != 200 or not item['model_id_matches_config'] or item['action_count'] < 2
                   for item in output.values()):
                raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())

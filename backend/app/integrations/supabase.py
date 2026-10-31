import asyncio
import logging
import httpx
from fastapi import Request, HTTPException
from app.core.config import Settings
from app.core.errors import ServiceUnavailable, SupabaseRequestError, UpstreamError


TABLES = {"profiles", "zones", "climate_observations", "air_quality_observations", "weather_forecasts", "risk_predictions", "prediction_explanations", "infrastructure", "osm_roads", "osm_import_runs", "waterways", "zone_dataset_metrics", "impact_assessments", "priority_assessments", "ai_recommendations", "incident_reports", "alerts", "audit_logs"}


class SupabaseGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(settings.external_timeout_seconds), limits=httpx.Limits(max_connections=50, max_keepalive_connections=10))

    async def close(self) -> None:
        await self.client.aclose()

    def _base(self) -> str:
        if not self.settings.configured:
            raise ServiceUnavailable("Supabase is not configured.")
        assert self.settings.supabase_url is not None
        return self.settings.supabase_url.rstrip("/")

    async def request(self, method: str, path: str, *, token: str | None = None, privileged: bool = False, params: dict | None = None, json: dict | list | None = None, prefer: str | None = None) -> object:
        base = self._base()
        key = self.settings.supabase_secret_key if privileged else self.settings.supabase_publishable_key
        if not key:
            raise ServiceUnavailable("Supabase server credentials are not configured.")
        headers = {"apikey": key, "Accept": "application/json"}
        # Legacy service-role JWTs need an Authorization header to bypass RLS.
        # Modern sb_secret_ keys are sent only as apikey, per Supabase's gateway format.
        if privileged and key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {key}"
        if token and not privileged:
            headers["Authorization"] = f"Bearer {token}"
        if prefer:
            headers["Prefer"] = prefer
        attempts = 3 if method.upper() == "GET" else 1
        for attempt in range(attempts):
            try:
                response = await self.client.request(method, f"{base}{path}", headers=headers, params=params, json=json)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt + 1 == attempts:
                    raise UpstreamError("Supabase network failure") from exc
                await asyncio.sleep(0.2 * (2 ** attempt))
                continue
            if response.status_code in (502, 503, 504) and attempt + 1 < attempts:
                await asyncio.sleep(0.2 * (2 ** attempt))
                continue
            if response.status_code >= 400:
                if response.status_code in (401, 403):
                    raise HTTPException(response.status_code, "Access denied by data service.")
                try:
                    error_body = response.json()
                except ValueError:
                    error_body = None
                error_code = error_body.get("code") if isinstance(error_body, dict) else None
                logging.getLogger("climaguard.supabase").warning(
                    "Supabase rejected %s %s: status=%s code=%s",
                    method.upper(), path, response.status_code, error_code or "unknown")
                raise SupabaseRequestError(response.status_code, error_code)
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        raise UpstreamError("Supabase retry exhausted")

    async def user(self, token: str) -> dict:
        result = await self.request("GET", "/auth/v1/user", token=token)
        if not isinstance(result, dict) or not result.get("id"):
            raise UpstreamError("Invalid Auth user response")
        return result

    async def table(self, table: str, method: str = "GET", *, token: str | None = None, privileged: bool = False, params: dict | None = None, json: dict | list | None = None, prefer: str | None = None) -> object:
        if table not in TABLES:
            raise ValueError("Unknown table")
        return await self.request(method, f"/rest/v1/{table}", token=token, privileged=privileged, params=params, json=json, prefer=prefer)


def get_gateway(request: Request) -> SupabaseGateway:
    return request.app.state.supabase

"""Nugen chat-completions client using the verified standalone request format."""

import asyncio
from datetime import datetime, timezone
import json
import logging
import re
import httpx
from pydantic import ValidationError
from app.core.config import Settings
from app.core.errors import NugenFailure
from app.schemas.nugen import NugenChatResponse, NugenGuidanceText, NugenInference, NugenStatus, unsupported_number


class NugenClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(settings.nugen_timeout_seconds))
        self.owns_client = client is None
        self.last_success_at: datetime | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.nugen_api_key and self.settings.nugen_model_id)

    def status(self) -> NugenStatus:
        available = bool(self.configured and self.last_success_at and (datetime.now(timezone.utc) - self.last_success_at).total_seconds() < 1800)
        return NugenStatus(configured=self.configured, available=available,
                           model_id=self.settings.nugen_model_id if self.configured else None,
                           last_success_at=self.last_success_at,
                           detail="Real Nugen inference succeeded recently." if available else "Nugen credentials are missing." if not self.configured else "Configured; awaiting a successful inference check.")

    async def close(self) -> None:
        if self.owns_client:
            await self.client.aclose()

    async def generate(self, prompt: str, *, allowed_numbers: set[str]) -> NugenInference:
        if not self.configured:
            raise NugenFailure("Nugen guidance is not configured.", "nugen_not_configured")
        if not prompt.strip() or len(prompt) > 12000:
            raise ValueError("Nugen prompt must be nonempty and at most 12000 characters")
        payload = {"model": self.settings.nugen_model_id, "messages": [{"role": "user", "content": prompt}],
                   "temperature": 0.2, "max_tokens": 400, "prompt_truncate_len": 3000, "stream": False}
        headers = {"Authorization": f"Bearer {self.settings.nugen_api_key}", "Content-Type": "application/json"}
        validation_failures = 0
        for attempt in range(3):
            try:
                response = await self.client.post(self.settings.nugen_inference_url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                if attempt == 2:
                    raise NugenFailure("Nugen took too long to respond. Retry shortly.", "nugen_timeout", 504) from exc
                await asyncio.sleep(0.5 * 2**attempt)
                continue
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise NugenFailure("Nugen could not be reached. Retry shortly.", "nugen_network") from exc
                await asyncio.sleep(0.5 * 2**attempt)
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                retry_after = response.headers.get("Retry-After", "")
                delay = min(float(retry_after), 5) if re.fullmatch(r"\d+(\.\d+)?", retry_after) else 0.5 * 2**attempt
                await asyncio.sleep(delay)
                continue
            if response.status_code >= 400:
                logging.getLogger("climaguard.nugen").warning("nugen_status=%s", response.status_code)
                if response.status_code in (401, 403):
                    raise NugenFailure("Nugen rejected the server credentials. Contact the application operator.", "nugen_auth")
                if response.status_code == 429:
                    raise NugenFailure("Nugen is rate-limited. Retry shortly.", "nugen_rate_limited")
                if response.status_code in (500, 502, 503, 504):
                    raise NugenFailure("Nugen is temporarily unavailable. Retry shortly.", "nugen_provider_unavailable")
                raise NugenFailure("Nugen rejected the inference request. Contact the application operator.", "nugen_request_rejected", 502)
            finish_reason = None
            try:
                provider = NugenChatResponse.model_validate(response.json())
                finish_reason = provider.choices[0].finish_reason
                if provider.model != self.settings.nugen_model_id:
                    raise NugenFailure("Nugen returned a different model than configured.", "nugen_model_mismatch", 502)
                if finish_reason == "length":
                    raise NugenFailure("Nugen stopped before completing guidance. Retry shortly.", "nugen_truncated", 502)
                content = provider.choices[0].message.content.strip()
                if content.startswith("```"):
                    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE).strip()
                parsed = json.loads(content)
                if isinstance(parsed, dict) and isinstance(parsed.get("risk_explanation"), str) and unsupported_number(parsed["risk_explanation"], allowed_numbers):
                    # A model may restate a sourced metric incorrectly. Drop only this
                    # optional prose; the service supplies a deterministic explanation.
                    parsed["risk_explanation"] = None
                guidance = NugenGuidanceText.model_validate(parsed, context={"allowed_numbers": allowed_numbers})
            except (ValueError, TypeError, KeyError, ValidationError) as exc:
                fields = [(tuple(error.get("loc", ())), error.get("type")) for error in exc.errors()] if isinstance(exc, ValidationError) else []
                safety_rejected = isinstance(exc, ValidationError) and any(
                    "unsupported numerical claim" in str(error.get("ctx", {}).get("error", ""))
                    for error in exc.errors())
                code = "nugen_safety_rejected" if safety_rejected else "nugen_invalid_response"
                logging.getLogger("climaguard.nugen").warning(
                    "nugen_rejection code=%s type=%s fields=%s finish_reason=%s attempt=%s",
                    code, type(exc).__name__, fields, finish_reason, attempt + 1)
                validation_failures += 1
                if validation_failures == 1 and attempt < 2:
                    payload["messages"][0]["content"] = prompt + (
                        "\nIMPORTANT: Return one complete JSON object with exactly three unnumbered action sentences. "
                        "Do not include digits, percentages, phone numbers, or unsupported measurements in any field.")
                    continue
                detail = ("Nugen guidance failed safety checks; no advice was shown. Retry."
                          if safety_rejected else "Nugen returned an invalid guidance format. Retry.")
                raise NugenFailure(detail, code, 503 if safety_rejected else 502) from exc
            self.last_success_at = datetime.now(timezone.utc)
            return NugenInference(guidance=guidance, model_id=provider.model,
                                  provider_request_id=provider.id, inferred_at=self.last_success_at)
        raise NugenFailure("Nugen guidance is temporarily unavailable. Retry shortly.", "nugen_provider_unavailable")

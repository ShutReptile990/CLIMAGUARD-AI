from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_secret_key: str | None = Field(default=None, repr=False)
    nugen_api_key: str | None = Field(default=None, repr=False)
    nugen_model_id: str | None = None
    nugen_inference_url: str = "https://api.nugen.in/api/v3/inference/chat/completions"
    nugen_timeout_seconds: float = Field(default=90, ge=10, le=120)
    external_timeout_seconds: float = Field(default=8, ge=1, le=30)
    flood_moderate_index: float = Field(default=25, ge=0, le=100)
    flood_high_index: float = Field(default=50, ge=0, le=100)
    flood_severe_index: float = Field(default=75, ge=0, le=100)
    heat_moderate_c: float = Field(default=32, ge=20, le=60)
    heat_high_c: float = Field(default=40, ge=20, le=60)
    heat_severe_c: float = Field(default=50, ge=20, le=70)

    @model_validator(mode="after")
    def ordered_risk_thresholds(self):
        if not (self.flood_moderate_index < self.flood_high_index < self.flood_severe_index and self.heat_moderate_c < self.heat_high_c < self.heat_severe_c):
            raise ValueError("Risk thresholds must be strictly increasing")
        return self

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()

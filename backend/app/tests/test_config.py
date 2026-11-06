import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_are_normalized_and_deduplicated():
    settings = Settings(
        _env_file=None,
        app_env="production",
        cors_origins="https://climaguard.example,https://climaguard.example/",
    )
    assert settings.origins == ["https://climaguard.example"]


@pytest.mark.parametrize(
    "origins",
    ["*", "http://climaguard.example", "https://climaguard.example/path", ""],
)
def test_production_cors_fails_closed_for_unsafe_origins(origins):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", cors_origins=origins)

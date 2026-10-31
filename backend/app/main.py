from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging, RequestLogMiddleware
from app.integrations.supabase import SupabaseGateway
from app.schemas.common import Health
from app.api import profile, incidents, alerts, data, snapshot
from app.api import environment, geography, analysis, nugen
from app.services.open_meteo import OpenMeteo
from app.services.environment import EnvironmentService
from app.services.analysis import AnalysisService
from app.integrations.nugen import NugenClient
from app.services.nugen_guidance import NugenGuidanceService

settings = get_settings()
configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.supabase = SupabaseGateway(settings)
    app.state.open_meteo = OpenMeteo(timeout_seconds=settings.external_timeout_seconds)
    app.state.environment = EnvironmentService(app.state.open_meteo, app.state.supabase)
    app.state.analysis = AnalysisService(app.state.environment, app.state.supabase)
    app.state.nugen = NugenClient(settings)
    app.state.nugen_guidance = NugenGuidanceService(app.state.nugen, app.state.analysis, app.state.supabase)
    yield
    await app.state.open_meteo.close()
    await app.state.supabase.close()
    await app.state.nugen.close()

app = FastAPI(title="CLIMAGUARD AI API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])
app.add_middleware(RequestLogMiddleware)
install_exception_handlers(app)
for router in (profile.router, incidents.router, alerts.router, data.router, snapshot.router, environment.router, geography.router, analysis.router, nugen.router):
    app.include_router(router, prefix="/api")
    app.include_router(router, prefix="/api/v1", include_in_schema=False)


@app.get("/api/health", response_model=Health, tags=["health"])
@app.get("/api/v1/health", response_model=Health, include_in_schema=False)
def health() -> Health:
    return Health(status="ok", service="climaguard-api", database_configured=settings.configured)

"""Application settings loaded from environment variables / .env file."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "OmniWatch"
    app_env: str = "development"
    debug: bool = False
    demo_mode: bool = False

    # Security
    secret_key: str = "CHANGE-ME-LONG-RANDOM-STRING"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 30
    jwt_refresh_ttl_days: int = 7
    jwt_action_ttl_minutes: int = 10

    # Supabase (set SUPABASE_URL + SUPABASE_JWT_SECRET to enable Supabase Auth).
    # DATABASE_URL should point at Supabase Postgres in that mode.
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""    # server-side only — never sent to the frontend
    supabase_service_key: str = ""   # optional; used by provisioning scripts only

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_jwt_secret)

    # Database
    database_url: str = "sqlite:///./data/omniwatch.db"
    db_admin_url: str = ""  # used only by the one-shot migrate container
    auto_create_tables: bool = True  # dev convenience; production uses migrate step

    # Redis / Celery
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str = ""
    celery_result_backend: str = ""
    celery_ingest_seconds: int = 30

    # HTTP
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    enable_hsts: bool = False

    # Rate limits (per IP) for sensitive flows.
    rate_login: str = "10/minute"
    rate_refresh: str = "20/minute"
    rate_action: str = "10/minute"
    rate_upload: str = "30/minute"
    rate_qr_scan: str = "30/minute"
    rate_dispatch: str = "20/minute"

    # Files & uploads
    upload_dir: str = "./data/uploads"
    max_photo_mb: int = 15
    max_video_mb: int = 60

    # Geofence (reference: 50 m, server-side validation)
    default_geofence_radius_m: float = 50.0

    # CV
    cv_mode: str = "auto"  # auto | real | sim
    yolo_model_path: str = ""
    cv_sample_every_frames: int = 5

    # Seed
    seed_on_start: bool = False  # demo/demo-mode bootstrap

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def docs_enabled(self) -> bool:
        return self.debug or self.app_env != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

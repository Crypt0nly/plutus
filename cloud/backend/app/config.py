from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    debug: bool = True
    secret_key: str = "change-me-in-production"

    # Clerk
    clerk_publishable_key: str = ""
    clerk_secret_key: str = ""
    clerk_jwks_url: str = "https://api.clerk.com/v1/jwks"

    # Database
    database_url: str = "postgresql+asyncpg://plutus:plutus@localhost:5432/plutus"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Agent
    default_llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Workspace — per-user file storage
    workspace_root: str = "/data/workspaces"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

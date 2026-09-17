from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+pg8000://postgres:postgres@localhost:5432/mk_billers"
    jwt_secret_key: str = "mk-billers2000"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    cors_origins: str = "https://mkbillers.netlify.app"
    seed_admin_email: str | None = None
    seed_admin_password: str | None = None
    seed_company_name: str = "MK-BILLERS"
    seed_company_phone: str | None = None
    seed_company_address: str | None = None
    seed_company_gst_number: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "no-reply@mk-billers.local"
    smtp_from_name: str = "MK-BILLERS"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    invite_code_expire_minutes: int = 60
    non_super_admin_bill_limit: int = 6

    class Config:
        env_file = ".env"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()

from pathlib import Path
import os
import environ

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    SECURE_SSL_REDIRECT=(bool, False),
    SESSION_COOKIE_SECURE=(bool, False),
    CSRF_COOKIE_SECURE=(bool, False),
    AUTO_PUBLISH_CONFIDENCE=(float, 0.97),
    ENABLE_COMPETITOR_DISCOVERY=(bool, False),
    AI_WEB_DISCOVERY_ENABLED=(bool, False),
    GOOGLE_INDEXING_ENABLED=(bool, False),
    PUBLIC_JOB_SCHEMA_ENABLED=(bool, True),
    RATE_LIMIT_PER_MINUTE=(int, 180),
    POST_RATE_LIMIT_PER_MINUTE=(int, 40),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-dev-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG")
ALLOWED_HOSTS = [x.strip() for x in env("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",") if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in env("DJANGO_CSRF_TRUSTED_ORIGINS", default="").split(",") if x.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "portal",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "portal.middleware.RateLimitMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "portal.middleware.StaffTOTP2FAMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "portal.middleware.SecurityHeadersMiddleware",
]
ROOT_URLCONF = "sarkarinaukri.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "portal.views.site_context",
    ]},
}]
WSGI_APPLICATION = "sarkarinaukri.wsgi.application"
ASGI_APPLICATION = "sarkarinaukri.asgi.application"

DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/account/"
LOGOUT_REDIRECT_URL = "/"

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}

SITE_NAME = env("SITE_NAME", default="SarkariNaukri")
SITE_URL = env("SITE_URL", default="http://localhost:8000").rstrip("/")
ADMIN_EMAIL = env("ADMIN_EMAIL", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="alerts@sarkarinaukri.local")
AUTO_PUBLISH_CONFIDENCE = env.float("AUTO_PUBLISH_CONFIDENCE")
ENABLE_COMPETITOR_DISCOVERY = env.bool("ENABLE_COMPETITOR_DISCOVERY")
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_MODEL = env("OPENAI_MODEL", default="gpt-5-mini")
AI_WEB_DISCOVERY_ENABLED = env.bool("AI_WEB_DISCOVERY_ENABLED")
WEB_DISCOVERY_MODEL = env("WEB_DISCOVERY_MODEL", default="gpt-5.4-mini")
PUBLIC_JOB_SCHEMA_ENABLED = env.bool("PUBLIC_JOB_SCHEMA_ENABLED")

CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 600
CELERY_TASK_SOFT_TIME_LIMIT = 540
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE_FILENAME = "/tmp/celerybeat-schedule"

# Redis-backed cache makes throttling and distributed coordination consistent across web workers.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache" if env("REDIS_URL", default="") else "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": env("REDIS_URL", default="sarkarinaukri-local-cache"),
    }
}
RATE_LIMIT_PER_MINUTE = env.int("RATE_LIMIT_PER_MINUTE")
POST_RATE_LIMIT_PER_MINUTE = env.int("POST_RATE_LIMIT_PER_MINUTE")

# Email alerts. In development this defaults to console; production should set SMTP_* values.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_TIMEOUT = 20

# Optional browser push.
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", default="")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", default="")
VAPID_SUBJECT = env("VAPID_SUBJECT", default=f"mailto:{ADMIN_EMAIL}" if ADMIN_EMAIL else "mailto:admin@example.com")

# Optional Search Console / Google Indexing API integration.
GOOGLE_INDEXING_ENABLED = env.bool("GOOGLE_INDEXING_ENABLED")
GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON = env("GOOGLE_INDEXING_SERVICE_ACCOUNT_JSON", default="")

# Optional staff-wide TOTP second factor. Generate a random base32 secret and keep it only in secrets storage.
ADMIN_TOTP_SECRET = env("ADMIN_TOTP_SECRET", default="")

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT")
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE")
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.05, send_default_pii=False)

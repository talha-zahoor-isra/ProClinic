import os
from pathlib import Path
from datetime import timedelta

import environ
from django.core.exceptions import ImproperlyConfigured

# 1. Environment variables
env = environ.Env(
    DEBUG=(bool, False),
    DATABASE_URL=(str, None),
    SECURE_SSL_REDIRECT=(bool, False),
    SESSION_COOKIE_SECURE=(bool, False),
    CSRF_COOKIE_SECURE=(bool, False),
    SECURE_HSTS_SECONDS=(int, 0),
    SECURE_HSTS_INCLUDE_SUBDOMAINS=(bool, False),
    SECURE_HSTS_PRELOAD=(bool, False),
)

# 2. Project paths
BASE_DIR = Path(__file__).resolve().parent.parent

# 3. Load local .env file, if present
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# 4. Core security settings
IS_RENDER = os.environ.get("RENDER", "").lower() == "true"

SECRET_KEY = env("SECRET_KEY", default="")
if IS_RENDER and not SECRET_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY must be configured in the Render environment."
    )
if not SECRET_KEY:
    SECRET_KEY = "local-development-only-insecure-key"

DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1"],
)

# 5. Installed applications
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "corsheaders",
    "cloudinary",
    "cloudinary_storage",
    "api",
    "accounts",
    "patients",
    "appointments",
    "prescriptions",
    "billing",
    "publications",
    "audit",
]

# 6. Middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "audit.middleware.AuditUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

# 7. Templates
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR.parent / "frontend" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

# 8. Database
# Render must use PostgreSQL; SQLite is for local development only.
_database_url = env("DATABASE_URL", default=None)

if IS_RENDER and not _database_url:
    raise ImproperlyConfigured(
        "DATABASE_URL must be configured on Render."
    )

if _database_url:
    DATABASES = {
        "default": env.db_url("DATABASE_URL"),
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        },
    }

# 9. Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# 10. Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

# 11. Static files and WhiteNoise
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    BASE_DIR.parent / "frontend" / "static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"

# 12. Media storage
_CLOUDINARY_CONFIGURED = bool(
    os.environ.get("CLOUDINARY_CLOUD_NAME")
    and os.environ.get("CLOUDINARY_API_KEY")
    and os.environ.get("CLOUDINARY_API_SECRET")
)

STORAGES = {
    "default": {
        "BACKEND": (
            "cloudinary_storage.storage.MediaCloudinaryStorage"
            if _CLOUDINARY_CONFIGURED
            else "django.core.files.storage.FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
    "API_KEY": os.environ.get("CLOUDINARY_API_KEY", ""),
    "API_SECRET": os.environ.get("CLOUDINARY_API_SECRET", ""),
}

if not _CLOUDINARY_CONFIGURED:
    try:
        MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.CustomUser"

# 13. Password hashing
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

# 14. Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "api.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
}

# 15. SimpleJWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# 16. Authentication redirects
LOGIN_URL = "/accounts/choose-login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/choose-login/"

# 17. Clinic configuration
CONSULTATION_FEE = env("CONSULTATION_FEE", default="500.00")
GST_RATE = env("GST_RATE", default="0.18")

# 18. CORS
# Configure exact frontend origins in the environment when needed.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[],
)

# 19. CSRF and production HTTPS
# Configure exact origins, such as https://app.talmedix.com.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[],
)

# Render terminates HTTPS at its proxy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = env.bool(
    "SECURE_SSL_REDIRECT", default=False
)
SESSION_COOKIE_SECURE = env.bool(
    "SESSION_COOKIE_SECURE", default=False
)
CSRF_COOKIE_SECURE = env.bool(
    "CSRF_COOKIE_SECURE", default=False
)
SECURE_HSTS_SECONDS = env.int(
    "SECURE_HSTS_SECONDS", default=0
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False
)
SECURE_HSTS_PRELOAD = env.bool(
    "SECURE_HSTS_PRELOAD", default=False
)

# 20. Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "accounts": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# 21. Email configuration
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("GMAIL_USER", default="")
EMAIL_HOST_PASSWORD = env("GMAIL_PASS", default="")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

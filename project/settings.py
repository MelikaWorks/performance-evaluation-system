import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False), ALLOWED_HOSTS=(list, []))
env.read_env(str(BASE_DIR / ".env"))

SECRET_KEY = env.str("SECRET_KEY", "change-me")
DEBUG = env.bool("DEBUG", False)

ALLOWED_HOSTS = ["127.0.0.1", "localhost", "192.168.1.5"]
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://192.168.1.5:8000",
]

# کوکی‌ها برای توسعه (HTTP)
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# سشن با بستن مرورگر حذف شود (دلخواه)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# مسیرهای احراز هویت
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/eval/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"


STATIC_URL = "/static/"
STATICFILES_DIRS = [
    BASE_DIR / "core" / "static",
]

# زبان و بومی‌سازی
LANGUAGE_CODE = "fa"
USE_I18N = True
TIME_ZONE = "Asia/Tehran"
USE_TZ = True

LANGUAGES = [
    ("fa", "Persian"),
    ("en", "English"),
]

INSTALLED_APPS = [
    "core.apps.CoreConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_select2",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",  # اگر لازم نداری، همینطور کامنت بماند
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "project.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            "django.template.context_processors.i18n",
            "core.context_processors.global_settings",
        ],
    },
}]

WSGI_APPLICATION = "project.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env.str("DB_NAME"),
        "USER": env.str("DB_USER"),
        "PASSWORD": env.str("DB_PASSWORD"),
        "HOST": env.str("DB_HOST", "127.0.0.1"),
        "PORT": env.str("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    # === validation of password===== پیش فرض بررسی پسورد جنگو
    # {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    # {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    # {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    # {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    # ===but ==== simple password
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 3}},
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

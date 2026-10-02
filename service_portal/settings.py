import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
APP_ENV = os.getenv("APP_ENV", "development")
SECRET_KEY = os.getenv("AUTH_SECRET", "unsafe-development-secret-change-me")
APP_URL = os.getenv("APP_URL", "http://localhost:8000")
if APP_ENV == "production":
    if SECRET_KEY == "unsafe-development-secret-change-me" or len(SECRET_KEY)<50: raise RuntimeError("AUTH_SECRET must be configured with at least 50 characters in production")
    if not os.getenv("APP_URL"): raise RuntimeError("APP_URL must be configured in production")
DEBUG = APP_ENV != "production"
ALLOWED_HOSTS = [x.strip() for x in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "portal",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
    "portal.middleware.ForcePasswordChangeMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "service_portal.urls"
TEMPLATES = [{"BACKEND":"django.template.backends.django.DjangoTemplates","DIRS":[BASE_DIR/"templates"],"APP_DIRS":True,"OPTIONS":{"context_processors":["django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages","portal.context.portal_context"]}}]
WSGI_APPLICATION = "service_portal.wsgi.application"

db_url = os.getenv("DATABASE_URL", "")
db_parts={k:os.getenv(k,"") for k in ("POSTGRES_DB","POSTGRES_USER","POSTGRES_PASSWORD","POSTGRES_HOST","POSTGRES_PORT")}
if db_url.startswith("postgres"):
    import urllib.parse
    u = urllib.parse.urlparse(db_url)
    DATABASES = {"default":{"ENGINE":"django.db.backends.postgresql","NAME":u.path.lstrip("/"),"USER":urllib.parse.unquote(u.username or ""),"PASSWORD":urllib.parse.unquote(u.password or ""),"HOST":u.hostname,"PORT":u.port or 5432,"CONN_MAX_AGE":60,"OPTIONS":{"sslmode":os.getenv("DB_SSLMODE","prefer")}}}
elif all(db_parts[k] for k in ("POSTGRES_DB","POSTGRES_USER","POSTGRES_PASSWORD","POSTGRES_HOST")):
    DATABASES = {"default":{"ENGINE":"django.db.backends.postgresql","NAME":db_parts["POSTGRES_DB"],"USER":db_parts["POSTGRES_USER"],"PASSWORD":db_parts["POSTGRES_PASSWORD"],"HOST":db_parts["POSTGRES_HOST"],"PORT":db_parts["POSTGRES_PORT"] or 5432,"CONN_MAX_AGE":60,"OPTIONS":{"sslmode":os.getenv("DB_SSLMODE","prefer")}}}
else:
    if APP_ENV=="production": raise RuntimeError("Production requires DATABASE_URL or complete POSTGRES_* settings")
    sqlite_url=db_url or "sqlite:///db.sqlite3"; DATABASES = {"default":{"ENGINE":"django.db.backends.sqlite3","NAME":BASE_DIR/(sqlite_url.removeprefix("sqlite:///") or "db.sqlite3")}}

AUTH_USER_MODEL = "portal.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME":"django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME":"django.contrib.auth.password_validation.MinimumLengthValidator","OPTIONS":{"min_length":10}},
    {"NAME":"django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME":"django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher", "django.contrib.auth.hashers.PBKDF2PasswordHasher"]
LANGUAGE_CODE, TIME_ZONE, USE_I18N, USE_TZ = "fa", "Asia/Tehran", True, True
STATIC_URL, STATIC_ROOT = "/static/", BASE_DIR/"staticfiles"
STATICFILES_DIRS = [BASE_DIR/"static"]
STORAGES = {"staticfiles":{"BACKEND":"whitenoise.storage.CompressedManifestStaticFilesStorage" if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage"}}
if os.getenv("FILE_STORAGE_TYPE", "local").lower() == "s3":
    if APP_ENV=="production" and not all(os.getenv(k) for k in ("S3_ENDPOINT","S3_BUCKET","S3_ACCESS_KEY","S3_SECRET_KEY")): raise RuntimeError("All S3 settings are required when FILE_STORAGE_TYPE=s3")
    STORAGES["default"] = {"BACKEND":"storages.backends.s3.S3Storage"}
    AWS_S3_ENDPOINT_URL=os.getenv("S3_ENDPOINT"); AWS_STORAGE_BUCKET_NAME=os.getenv("S3_BUCKET")
    AWS_ACCESS_KEY_ID=os.getenv("S3_ACCESS_KEY"); AWS_SECRET_ACCESS_KEY=os.getenv("S3_SECRET_KEY")
    AWS_QUERYSTRING_AUTH=True; AWS_DEFAULT_ACL=None
else:
    STORAGES["default"]={"BACKEND":"django.core.files.storage.FileSystemStorage"}
    MEDIA_ROOT=Path(os.getenv("UPLOAD_PATH", BASE_DIR/"uploads")); MEDIA_URL="/media/"
MAX_UPLOAD_SIZE=int(os.getenv("MAX_UPLOAD_SIZE", 10*1024*1024))
REPORT_AT_RISK_RATIO=float(os.getenv("REPORT_AT_RISK_RATIO", "0.8"))
if not 0 < REPORT_AT_RISK_RATIO <= 1: raise RuntimeError("REPORT_AT_RISK_RATIO must be in (0, 1]")
LOGIN_MAX_FAILURES=int(os.getenv("LOGIN_MAX_FAILURES","5")); LOGIN_LOCK_MINUTES=int(os.getenv("LOGIN_LOCK_MINUTES","15"))
ALLOWED_UPLOAD_EXTENSIONS=set(os.getenv("ALLOWED_UPLOAD_EXTENSIONS","pdf,doc,docx,xls,xlsx,ppt,pptx,png,jpg,jpeg,zip").lower().split(","))
LOGIN_URL="login"; LOGIN_REDIRECT_URL="home"; LOGOUT_REDIRECT_URL="login"
SESSION_COOKIE_HTTPONLY=True; SESSION_COOKIE_SAMESITE="Lax"; CSRF_COOKIE_SAMESITE="Lax"
SESSION_COOKIE_SECURE=APP_ENV=="production"; CSRF_COOKIE_SECURE=APP_ENV=="production"; SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO","https")
SECURE_CONTENT_TYPE_NOSNIFF=True; X_FRAME_OPTIONS="DENY"; SECURE_REFERRER_POLICY="same-origin"
SECURE_HSTS_SECONDS=int(os.getenv("SECURE_HSTS_SECONDS","31536000" if APP_ENV=="production" else "0")); SECURE_HSTS_INCLUDE_SUBDOMAINS=APP_ENV=="production"; SECURE_HSTS_PRELOAD=APP_ENV=="production"
SECURE_SSL_REDIRECT=os.getenv("SECURE_SSL_REDIRECT","true" if APP_ENV=="production" else "false").lower()=="true"
DEFAULT_AUTO_FIELD="django.db.models.BigAutoField"
EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"

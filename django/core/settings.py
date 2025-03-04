"""
Django settings for core project.

Generated by 'django-admin startproject' using Django 4.2.11.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

from pathlib import Path
import os, time
from dotenv import load_dotenv

load_dotenv()


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

#TIME_ZONE = 'Europe/Warsaw'

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-h%3vpt@om%_05h4yih^ws#*8ktkow3zsr9l(e!u3ri1vh&9$^&"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# if DEBUG:
#     print("\n", os.getcwd(), os.listdir(os.getcwd()), os.environ)
#     print(
#         *[
#             "NAME" + (os.getenv("POSTGRES_DATA") or "Not Set"),
#             "USER" + (os.getenv("POSTGRES_USER") or "Not Set"),
#             "PASSWORD" + (os.getenv("POSTGRES_PASS") or "Not Set"),
#             "HOST" + "postgres",
#             "PORT" + "5432",
#         ]
#     )
# time.sleep(3)


ALLOWED_HOSTS = [
    "localhost",
    *["192.168.1." + str(y) for y in range(0x100)],
    *["192.168.0." + str(y) for y in range(0x100)],
    *["192.168.59." + str(y) for y in range(0x100)],
    *["172.17.0." + str(y) for y in range(0x100)],
    *["172.18.0." + str(y) for y in range(0x100)],
    *["172.19.0." + str(y) for y in range(0x100)],
    *["172.20.0." + str(y) for y in range(0x100)],
]


# Application definition

INSTALLED_APPS = [
    "webui",
    "django_q",
    'django_elasticsearch_dsl',
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DATA"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASS"),
        "HOST": "postgres",
        "PORT": "5432",
    }
}

ELASTICSEARCH_DSL = {
    "default": {
        "hosts": "http://elastic:9200"  # 'elastic' is the service name from docker-compose
    },
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True
# MINIO

DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"

AWS_S3_ENDPOINT_URL = "minio:9000"  # MinIO service in Docker
AWS_ACCESS_KEY_ID = f"{os.getenv('MINIO_ACCESS_KEY')}"
AWS_SECRET_ACCESS_KEY = f"{os.getenv('MINIO_SECRET_KEY')}"
AWS_STORAGE_BUCKET_NAME = "breached-credentials"


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

Q_CLUSTER = {
    'name': 'leak_detection',
    'workers': 4,
    'recycle': 500,
    'timeout': 300,  # 5 minut
    'retry': 600,    # 10 minut – większe niż timeout
    'queue_limit': 5000,
    'orm': 'default',
}


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'webui': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'django_q': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'elasticsearch': {  # Added this
            'handlers': ['console'],
            'level': 'WARNING',  # Only log warnings/errors
        },
        'elastic_transport': {  # Added this
            'handlers': ['console'],
            'level': 'WARNING',
        },
    },
}
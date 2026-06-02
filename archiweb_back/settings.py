"""
Django settings for archiweb_back project.
"""
import os
from datetime import timedelta
from pathlib import Path
from corsheaders.defaults import default_headers
from dotenv import load_dotenv

# 1. On définit BASE_DIR EN PREMIER
BASE_DIR = Path(__file__).resolve().parent.parent

# 2. On force la lecture du .env avec son chemin absolu exact
load_dotenv(BASE_DIR / '.env')


def env_str(name, default=''):
    return os.getenv(name, default).strip()

def env_bool(name, default=False):
    return env_str(name, str(default)).lower() in ('1', 'true', 'yes', 'on')


def env_list(name):
    return [value.strip() for value in env_str(name).split(',') if value.strip()]

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env_str('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_bool('DJANGO_DEBUG', False)

STRAVA_CLIENT_ID = env_str('STRAVA_CLIENT_ID')
STRAVA_CLIENT_SECRET = env_str('STRAVA_CLIENT_SECRET')

ALLOWED_HOSTS = ['*']

# --- Application definition ---

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_filters',

    # --- Applications tierces ---
    'rest_framework',
    'corsheaders',
    'rest_framework_simplejwt',

    # --- Vos applications ---
    'core.apps.CoreConfig',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'archiweb_back.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'archiweb_back.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,  # Dit à SQLite d'attendre jusqu'à 20 secondes si la base est verrouillée
        }
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Europe/Paris'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- CONFIGURATION CORS ---
CORS_ALLOWED_ORIGINS = env_list('CORS_ALLOWED_ORIGINS')

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = list(default_headers) + [
    'cache-control',
    'x-requested-with',
    'content-type',
    'accept',
    'origin',
    'authorization',
]

# --- CONFIGURATION REST FRAMEWORK ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
}

# --- CONFIGURATION SIMPLE JWT ---
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

LOGIN_REDIRECT_URL = '/api/exercices/'
LOGOUT_REDIRECT_URL = '/api/exercices/'
CORS_ALLOW_ALL_ORIGINS = env_bool('CORS_ALLOW_ALL_ORIGINS', False)

# --- CONFIG EMAIL ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True

EMAIL_HOST_USER = env_str('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env_str('EMAIL_HOST_PASSWORD')

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# --- MEDIA FILES (MESSAGERIE) ---
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# --- FRONTEND URL (RESET PASSWORD) ---
# Lit l'URL depuis le .env du serveur.
FRONTEND_URL = env_str('FRONTEND_URL')

# --- EXPO DEV URL (pour tester les deep links avec Expo Go) ---
# Format : exp://IP:8081  — mettre à None en production
EXPO_DEV_URL = env_str('EXPO_DEV_URL')

# --- GOOGLE CALENDAR ---
GOOGLE_CLIENT_ID = env_str('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = env_str('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = env_str('GOOGLE_REDIRECT_URI')
GOOGLE_CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar"
]

# --- STRIPE CONFIGURATION ---
STRIPE_PUBLIC_KEY = env_str('STRIPE_PUBLIC_KEY')
STRIPE_SECRET_KEY = env_str('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = env_str('STRIPE_WEBHOOK_SECRET')
STRIPE_PREMIUM_PRICE_ID = 'price_1TXkjbC9OZTHr1sPOvQJsjwl'

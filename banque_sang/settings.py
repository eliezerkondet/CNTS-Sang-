import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Chemins de base du projet
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG') == 'True'
ALLOWED_HOSTS = ['*']

# Applications installées
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Ton application
    'blood_bank',
]

# Ton modèle utilisateur personnalisé (TRES IMPORTANT !)
AUTH_USER_MODEL = 'blood_bank.Utilisateur'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'banque_sang.urls' # (Vérifie que c'est bien le nom de ton dossier principal)

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')], # Si tu as un dossier templates global
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'banque_sang.wsgi.application'

# Base de données (SQLite pour l'instant)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Mots de passe
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

# Langue et heure (Congo)
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Brazzaville'
USE_I18N = True
USE_TZ = True

# Fichiers statiques (CSS, JS, Images de design)
STATIC_URL = 'static/'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Fichiers Médias (Photos de profil et QR CODES !)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Configuration Africa's Talking (Mode simulation pour l'instant)
AFRICASTALKING_USERNAME = os.getenv('AFRICASTALKING_USERNAME')
AFRICASTALKING_API_KEY = os.getenv('AFRICASTALKING_API_KEY')

# ==========================================
# CONFIGURATION EMAIL (SMTP GMAIL) - VRAIS EMAILS
# ==========================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True

# Ton adresse email dédiée au projet
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')

# LE CODE SECRET À 16 LETTRES GÉNÉRÉ PAR GOOGLE (Sans espaces)
# Remplace 'xxxx xxxx xxxx xxxx' par ton vrai code !
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')

# Le nom officiel qui s'affichera chez le destinataire
DEFAULT_FROM_EMAIL = 'CNTS Brazzaville <cntscongobrazzaville@gmail.com>'
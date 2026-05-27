from django.contrib.auth import get_user_model
import os
import sys

User = get_user_model()

username = os.getenv("DJANGO_SUPERUSER_USERNAME")
email = os.getenv("DJANGO_SUPERUSER_EMAIL")
password = os.getenv("DJANGO_SUPERUSER_PASSWORD")

# Vérification stricte
if not username or not password:
    print("❌ Variables DJANGO_SUPERUSER_USERNAME ou PASSWORD manquantes")
    sys.exit(1)

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(
        username=username,
        email=email or "",
        password=password
    )
    print("✅ Superuser créé avec succès.")
else:
    print("ℹ️ Le superuser existe déjà.")
"""
Create the initial platform superuser using environment variables.

Run after migrations. Existing accounts are not silently reset on
every deployment.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured

User = get_user_model()

username = os.environ.get("PLATFORM_ADMIN_USERNAME")
email = os.environ.get("PLATFORM_ADMIN_EMAIL")
password = os.environ.get("PLATFORM_ADMIN_PASSWORD")

if not all([username, email, password]):
raise ImproperlyConfigured(
"Set PLATFORM_ADMIN_USERNAME, PLATFORM_ADMIN_EMAIL, "
"and PLATFORM_ADMIN_PASSWORD before running create_admin.py."
)

if len(password) < 12:
raise ImproperlyConfigured(
"PLATFORM_ADMIN_PASSWORD must be at least 12 characters long."
)

if User.objects.filter(username=username).exists():
print(
f"Platform admin '{username}' already exists. "
"No account or password changes were made."
)
else:
User.objects.create_superuser(
username=username,
email=email,
password=password,
)
print(f"Platform superuser '{username}' created successfully.")

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounts.models import User

username = 'admin'
email = 'admin@example.com'
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

if not password:
    print('ERROR: DJANGO_SUPERUSER_PASSWORD not set')
elif User.objects.filter(username=username).exists():
    print(f'Superuser {username} already exists')
else:
    User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
        role='admin'
    )
    print(f'Superuser {username} created successfully')
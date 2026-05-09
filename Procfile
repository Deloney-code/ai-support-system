web: daphne -b 0.0.0.0 -p $PORT core.asgi:application
worker: celery -A core worker --loglevel=info --pool=solo
release: python manage.py migrate
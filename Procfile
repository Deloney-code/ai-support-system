web: python start.py
worker: celery -A core worker --loglevel=info --pool=solo
release: python manage.py migrate
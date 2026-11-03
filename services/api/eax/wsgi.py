"""Entry point for gunicorn: gunicorn eax.wsgi:app"""

from .app import create_app

app = create_app()

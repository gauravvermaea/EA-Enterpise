"""Entry point for gunicorn: gunicorn eax.wsgi:app"""

from . import coverage_probe

coverage_probe.start()          # EAX_COVERAGE=on: measured from here, before the rest is imported (D642)

from .app import create_app  # noqa: E402

app = create_app()

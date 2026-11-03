import os

import pytest

# Point the API at a database port nothing listens on, so tests never touch a real database.
os.environ.setdefault("EAX_DB_HOST", "127.0.0.1")
os.environ.setdefault("EAX_DB_PORT", "1")
os.environ.setdefault("EAX_DB_PASSWORD", "test")
os.environ.setdefault("EAX_HOSTNAME", "localhost")
os.environ.setdefault("EAX_HTTPS_PORT", "443")


@pytest.fixture()
def client():
    from eax.app import create_app

    app = create_app(testing=True)
    return app.test_client()

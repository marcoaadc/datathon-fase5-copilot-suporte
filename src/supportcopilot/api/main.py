"""Ponto de entrada ASGI: ``uvicorn supportcopilot.api.main:app``."""

from supportcopilot.api.app import create_app

app = create_app()

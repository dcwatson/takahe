"""
ASGI config for takahe project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "takahe.settings")

django_application = get_asgi_application()

from .streaming import StreamingClient


async def application(scope, receive, send):
    if scope["type"] == "http":
        await django_application(scope, receive, send)
    elif scope["type"] == "websocket":
        await StreamingClient(scope, receive, send).run()
    else:
        raise NotImplementedError(f"Unknown scope type {scope['type']}")

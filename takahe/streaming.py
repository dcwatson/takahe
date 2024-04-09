import asyncio
import json
import logging

from django.utils import timezone

from activities.services import TimelineService
from api.models import Token

logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.DEBUG)


class StreamingClient:
    def __init__(self, scope, receive, send):
        self.events = asyncio.Queue()
        self.running = False
        self.scope = scope
        self.receive = receive
        self.send = send
        self.streams = {}
        # IceCubes does this, maybe others too?
        self.token_value = self.scope["subprotocols"][0]

    async def handle_subscribe(self, stream, **kwargs):
        self.streams[stream] = kwargs

    async def handle_unsubscribe(self, stream, **kwargs):
        self.streams.pop(stream, None)

    async def handle_event(self, event):
        handler = getattr(self, "handle_" + event.pop("type"))
        await handler(**event)

    async def read_requests(self):
        while self.running:
            socket_event = await self.receive()
            match socket_event["type"]:
                case "websocket.connect":
                    await self.send({"type": "websocket.accept"})
                case "websocket.disconnect":
                    self.running = False
                case "websocket.receive":
                    try:
                        await self.handle_event(json.loads(socket_event["text"]))
                    except Exception:
                        logger.debug("ERROR HANDLING", socket_event)
                case _:
                    logger.debug("UNKNOWN EVENT %s", socket_event)

    async def send_event(self, streams, event, payload):
        if not self.running:
            return
        await self.send(
            {
                "type": "websocket.send",
                "text": json.dumps(
                    {
                        "stream": streams,
                        "event": event,
                        "payload": json.dumps(payload),
                    }
                ),
            }
        )

    async def stream_events(self):
        token = await Token.objects.select_related("identity__domain").aget(
            token=self.token_value, revoked=None
        )
        ts = TimelineService(token.identity)
        since = timezone.now()
        while self.running:
            await asyncio.sleep(5.0)
            if "user" in self.streams:
                async for e in ts.home().filter(created__gt=since):
                    await self.send_event(
                        ["user"], "update", e.to_mastodon_status_json()
                    )
                since = timezone.now()

    async def run(self):
        self.running = True
        async with asyncio.TaskGroup() as g:
            g.create_task(self.read_requests())
            g.create_task(self.stream_events())
        self.running = False

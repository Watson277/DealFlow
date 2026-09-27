from starlette.types import ASGIApp, Receive, Scope, Send

from app.models.mixins import utc_now


class RequestTimingMiddleware:
    """Capture upload arrival before FastAPI reads the multipart body."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            scope.setdefault("state", {})["request_started_at"] = utc_now()
        await self.app(scope, receive, send)

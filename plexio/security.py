import json
from collections.abc import Awaitable, Callable

from starlette.types import Message, Receive, Scope, Send

SECURITY_HEADERS = {
    'Content-Security-Policy': (
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
        "font-src 'self'; connect-src 'self' http: https:"
    ),
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
}


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                existing = {name.lower() for name, _ in headers}
                for name, value in SECURITY_HEADERS.items():
                    encoded_name = name.lower().encode('latin-1')
                    if encoded_name not in existing:
                        headers.append((encoded_name, value.encode('latin-1')))
                message['headers'] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_body_size: int):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or scope.get('method') not in {
            'POST',
            'PUT',
            'PATCH',
        }:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get('headers', []))
        try:
            content_length = int(headers.get(b'content-length', b'0'))
        except ValueError:
            content_length = 0
        if content_length > self.max_body_size:
            await self._reject(send)
            return

        messages: list[Message] = []
        total = 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            total += len(message.get('body', b''))
            if total > self.max_body_size:
                await self._reject(send)
                return
            messages.append(message)
            if not message.get('more_body', False):
                break

        async def replay() -> Message:
            if messages:
                return messages.pop(0)
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(send: Callable[[Message], Awaitable[None]]) -> None:
        body = json.dumps({'detail': 'Request body too large'}).encode()
        await send(
            {
                'type': 'http.response.start',
                'status': 413,
                'headers': [
                    (b'content-type', b'application/json'),
                    (b'content-length', str(len(body)).encode()),
                ],
            }
        )
        await send({'type': 'http.response.body', 'body': body})

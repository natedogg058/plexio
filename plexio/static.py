from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
    """Serve built assets and fall back to index.html for React routes."""

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or Path(path).suffix:
                raise
            return await super().get_response('index.html', scope)
        if response.status_code != 404 or Path(path).suffix:
            return response
        return await super().get_response('index.html', scope)

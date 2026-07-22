from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import asyncio
import urllib.request
import urllib.parse
import json

router = APIRouter()

PLEX_HEADERS = {
    'X-Plex-Product': 'Plexio',
    'X-Plex-Version': '1.0.0',
    'Accept': 'application/json',
}

def _fetch_pin(client_id: str) -> dict:
    req = urllib.request.Request(
        'https://plex.tv/api/v2/pins?strong=true',
        method='POST',
        data=b'',
        headers={**PLEX_HEADERS, 'X-Plex-Client-Identifier': client_id, 'Content-Length': '0'},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())

def _fetch_token(pin_id: str, code: str, client_id: str) -> dict:
    params = urllib.parse.urlencode({'code': code, 'X-Plex-Client-Identifier': client_id})
    url = f'https://plex.tv/api/v2/pins/{pin_id}?{params}'
    req = urllib.request.Request(url, headers={**PLEX_HEADERS, 'X-Plex-Client-Identifier': client_id})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())

def _fetch_resources(token: str, client_id: str) -> list:
    params = urllib.parse.urlencode({
        'includeHttps': 1,
        'includeRelay': 1,
        'X-Plex-Token': token,
        'X-Plex-Client-Identifier': client_id,
    })
    url = f'https://plex.tv/api/v2/resources?{params}'
    req = urllib.request.Request(url, headers={**PLEX_HEADERS, 'X-Plex-Client-Identifier': client_id})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())

@router.post('/api/v1/plex-pin')
async def create_plex_pin(request: Request):
    client_id = request.headers.get('X-Plex-Client-Identifier', '')
    data = await asyncio.to_thread(_fetch_pin, client_id)
    return JSONResponse(content=data)

@router.get('/api/v1/plex-token/{pin_id}')
async def get_plex_token(request: Request, pin_id: str, code: str = '', client_identifier: str = ''):
    client_id = client_identifier or request.headers.get('X-Plex-Client-Identifier', '')
    data = await asyncio.to_thread(_fetch_token, pin_id, code, client_id)
    return JSONResponse(content=data)

@router.get('/api/v1/plex-resources')
async def get_plex_resources(request: Request):
    # Read params by their actual names sent from the frontend
    params = dict(request.query_params)
    token = params.get('X-Plex-Token', '')
    client_id = params.get('X-Plex-Client-Identifier', '')
    data = await asyncio.to_thread(_fetch_resources, token, client_id)
    return JSONResponse(content=data)

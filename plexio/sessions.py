import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

import aiosqlite
from cryptography.fernet import Fernet, InvalidToken

from plexio.models.addon import AddonConfiguration

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    config_json  TEXT NOT NULL,
    label        TEXT,
    server_name  TEXT,
    created_at   TEXT NOT NULL,
    last_used_at TEXT,
    config_hash  TEXT
)
"""


class SessionCapacityError(RuntimeError):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _config_hash(config: dict) -> str:
    """Stable SHA-256 over the canonical JSON of a config, used to dedupe
    identical install configs to a single session. Not a security primitive --
    encryption at rest still protects the token; this only avoids minting a new
    session every time the configure page is submitted with an identical config."""
    canonical = json.dumps(config, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _init_fernet(settings) -> Fernet:
    """Resolve the Fernet key. An operator-provided SESSION_ENCRYPTION_KEY takes
    precedence; otherwise use (or create) a persistent key file next to the DB so
    tokens are encrypted at rest by default with no configuration required."""
    key = settings.session_encryption_key
    if key:
        return Fernet(key if isinstance(key, bytes) else key.encode())
    parent = os.path.dirname(settings.session_db_path) or '.'
    key_path = os.path.join(parent, 'session.key')
    if os.path.exists(key_path):
        with open(key_path, 'rb') as f:
            return Fernet(f.read().strip())
    new_key = Fernet.generate_key()
    with open(key_path, 'wb') as f:
        f.write(new_key)
    os.chmod(key_path, 0o600)
    return Fernet(new_key)


async def init_sessions(settings):
    """Open the SQLite session store and ensure the schema exists.

    Returns None when sessions are disabled, so callers can treat the
    feature as absent without special-casing elsewhere.
    """
    if not settings.enable_sessions:
        return None
    parent = os.path.dirname(settings.session_db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fernet = _init_fernet(settings)
    db = await aiosqlite.connect(settings.session_db_path)
    await db.execute(_CREATE_TABLE)
    # Migrate pre-0.4.3 databases: add config_hash if it is missing.
    async with db.execute('PRAGMA table_info(sessions)') as cur:
        columns = [r[1] for r in await cur.fetchall()]
    if 'config_hash' not in columns:
        await db.execute('ALTER TABLE sessions ADD COLUMN config_hash TEXT')
    await db.execute(
        'CREATE INDEX IF NOT EXISTS idx_sessions_config_hash ON sessions(config_hash)'
    )
    await db.commit()
    return SessionStore(db, fernet, max_sessions=settings.max_sessions)


class SessionStore:
    """Durable, server-side store mapping a session id to an addon config.

    The config is stored as the same camelCase JSON shape that legacy
    base64 install URLs carry, so it round-trips through AddonConfiguration
    exactly as the legacy decode path does.
    """

    def __init__(
        self,
        db: aiosqlite.Connection,
        fernet: Fernet,
        *,
        max_sessions: int = 1000,
    ):
        self._db = db
        self._fernet = fernet
        self._max_sessions = max_sessions
        self._create_lock = asyncio.Lock()

    async def create(self, config: dict, label: str | None = None) -> str:
        async with self._create_lock:
            return await self._create(config, label)

    async def _create(self, config: dict, label: str | None = None) -> str:
        config_hash = _config_hash(config)
        now = _utcnow()
        async with self._db.execute(
            'SELECT session_id FROM sessions WHERE config_hash = ?',
            (config_hash,),
        ) as cur:
            existing = await cur.fetchone()
        if existing is not None:
            # Identical config already stored -- reuse it rather than minting a
            # new session (e.g. clipboard then Install both submit the form).
            await self._db.execute(
                'UPDATE sessions SET last_used_at = ? WHERE session_id = ?',
                (now, existing[0]),
            )
            await self._db.commit()
            return existing[0]
        async with self._db.execute('SELECT COUNT(*) FROM sessions') as cur:
            count = (await cur.fetchone())[0]
        if count >= self._max_sessions:
            raise SessionCapacityError('Session capacity reached')
        session_id = str(uuid.uuid4())
        server_name = config.get('serverName') or config.get('server_name')
        payload = self._fernet.encrypt(json.dumps(config).encode()).decode()
        await self._db.execute(
            'INSERT INTO sessions '
            '(session_id, config_json, label, server_name, created_at, '
            'last_used_at, config_hash) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (session_id, payload, label, server_name, now, now, config_hash),
        )
        await self._db.commit()
        return session_id

    async def get_config(self, session_id: str) -> AddonConfiguration | None:
        async with self._db.execute(
            'SELECT config_json, config_hash FROM sessions WHERE session_id = ?',
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        stored, stored_hash = row[0], row[1]
        try:
            plain = self._fernet.decrypt(stored.encode()).decode()
            reencrypted = None
        except InvalidToken:
            # Legacy plaintext row (pre-0.4.1): read as-is, then migrate it.
            plain = stored
            reencrypted = self._fernet.encrypt(plain.encode()).decode()
        config = json.loads(plain)
        now = _utcnow()
        # Backfill config_hash for rows created before 0.4.3 so they dedupe too.
        config_hash = stored_hash or _config_hash(config)
        if reencrypted is not None:
            await self._db.execute(
                'UPDATE sessions SET config_json = ?, last_used_at = ?, '
                'config_hash = ? '
                'WHERE session_id = ?',
                (reencrypted, now, config_hash, session_id),
            )
        else:
            await self._db.execute(
                'UPDATE sessions SET last_used_at = ?, config_hash = ? '
                'WHERE session_id = ?',
                (now, config_hash, session_id),
            )
        await self._db.commit()
        return AddonConfiguration(**config)

    async def list(self) -> list[dict]:
        async with self._db.execute(
            'SELECT session_id, label, server_name, created_at, last_used_at '
            'FROM sessions ORDER BY created_at DESC'
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                'session_id': r[0],
                'label': r[1],
                'server_name': r[2],
                'created_at': r[3],
                'last_used_at': r[4],
            }
            for r in rows
        ]

    async def delete(self, session_id: str) -> bool:
        cur = await self._db.execute(
            'DELETE FROM sessions WHERE session_id = ?',
            (session_id,),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def ping(self) -> bool:
        """Cheap liveness check that the store responds to a query."""
        async with self._db.execute('SELECT 1') as cur:
            await cur.fetchone()
        return True

    async def close(self):
        await self._db.close()

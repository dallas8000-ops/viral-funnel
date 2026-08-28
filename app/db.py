from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import event

from app.models import Base
from app.settings import DB_PATH, get_settings


def _on_connect(dbapi_conn, _connection_record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA temp_store=MEMORY")
    cur.execute("PRAGMA cache_size=-64000")
    cur.execute("PRAGMA mmap_size=268435456")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def _engine():
    get_settings()
    url = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
    eng = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        connect_args={"timeout": 30},
    )
    event.listen(eng.sync_engine, "connect", _on_connect)
    return eng


engine = _engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

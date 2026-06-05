"""
database.py — SQLAlchemy models and DB connection.

Local dev:  DATABASE_URL=sqlite:///./windsite.db  (default)
Production: DATABASE_URL=postgresql://user:pass@host/db  (set as env var on Render)
            Use Neon free tier: https://neon.tech
"""

from __future__ import annotations
import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()  # loads backend/.env in local dev; no-op on Render (env vars set directly)

from sqlalchemy import (
    Column, Integer, String, Float, JSON, DateTime,
    UniqueConstraint, create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./windsite.db")

# Neon / Railway Postgres URLs start with "postgres://" — SQLAlchemy needs "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Simulation(Base):
    __tablename__ = "simulations"

    id             = Column(Integer, primary_key=True)
    polygon_hash   = Column(String(12), nullable=False)
    wind_direction = Column(Integer, nullable=False)
    wind_speed_ref = Column(Integer, nullable=False, default=10)
    payload        = Column(JSON, nullable=False)   # full grid_to_payload result
    created_at     = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("polygon_hash", "wind_direction", "wind_speed_ref"),
    )


class GeometryCache(Base):
    __tablename__ = "geometry_cache"

    id           = Column(Integer, primary_key=True)
    polygon_hash = Column(String(12), unique=True, nullable=False)
    data         = Column(JSON, nullable=False)   # full geometry result dict
    fetched_at   = Column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

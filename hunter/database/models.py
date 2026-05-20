"""
SQLAlchemy ORM models for the Meme Token Hunter database.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime,
    Text, Enum, JSON, ForeignKey, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class ChainType(str, enum.Enum):
    SOLANA = "solana"
    BSC = "bsc"
    ETHEREUM = "ethereum"
    BASE = "base"


class SafetyStatus(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    UNKNOWN = "unknown"


class AlertLevel(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Token(Base):
    """Represents a discovered token across any supported chain."""
    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    chain: Mapped[ChainType] = mapped_column(Enum(ChainType), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(256))
    symbol: Mapped[Optional[str]] = mapped_column(String(32))
    decimals: Mapped[Optional[int]] = mapped_column(Integer)

    # Discovery info
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    discovered_dex: Mapped[Optional[str]] = mapped_column(String(64))
    pool_address: Mapped[Optional[str]] = mapped_column(String(128))
    creator_address: Mapped[Optional[str]] = mapped_column(String(128), index=True)

    # Pricing
    initial_price_usd: Mapped[Optional[float]] = mapped_column(Float)
    current_price_usd: Mapped[Optional[float]] = mapped_column(Float)
    initial_liquidity_usd: Mapped[Optional[float]] = mapped_column(Float)
    current_liquidity_usd: Mapped[Optional[float]] = mapped_column(Float)
    market_cap_usd: Mapped[Optional[float]] = mapped_column(Float)

    # Safety analysis
    safety_score: Mapped[Optional[float]] = mapped_column(Float, index=True)
    is_honeypot: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_contract_verified: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_ownership_renounced: Mapped[Optional[bool]] = mapped_column(Boolean)
    lp_lock_duration_days: Mapped[Optional[int]] = mapped_column(Integer)
    lp_lock_percentage: Mapped[Optional[float]] = mapped_column(Float)
    top_holder_percentage: Mapped[Optional[float]] = mapped_column(Float)

    # Rug pull prediction
    rugpull_risk_score: Mapped[Optional[float]] = mapped_column(Float)
    prediction_model_version: Mapped[Optional[str]] = mapped_column(String(32))

    # Social
    social_score: Mapped[Optional[float]] = mapped_column(Float)
    twitter_mentions: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    telegram_mentions: Mapped[Optional[int]] = mapped_column(Integer, default=0)

    # Metadata
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    safety_checks = relationship("SafetyCheck", back_populates="token", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="token", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_tokens_chain_safety", "chain", "safety_score"),
        Index("ix_tokens_discovered_at_chain", "discovered_at", "chain"),
    )

    def __repr__(self) -> str:
        return f"<Token {self.symbol} ({self.chain.value}) @ {self.address[:12]}...>"


class SafetyCheck(Base):
    """Individual safety check result for a token."""
    __tablename__ = "safety_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[int] = mapped_column(Integer, ForeignKey("tokens.id"), nullable=False, index=True)
    check_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[SafetyStatus] = mapped_column(Enum(SafetyStatus), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text)
    score: Mapped[Optional[float]] = mapped_column(Float)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    token = relationship("Token", back_populates="safety_checks")


class Alert(Base):
    """Alert generated for a token event."""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_id: Mapped[int] = mapped_column(Integer, ForeignKey("tokens.id"), nullable=False, index=True)
    level: Mapped[AlertLevel] = mapped_column(Enum(AlertLevel), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent_telegram: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_discord: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    token = relationship("Token", back_populates="alerts")


class ScanState(Base):
    """Persistent state for chain scanners to track last processed blocks/slots."""
    __tablename__ = "scan_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chain: Mapped[ChainType] = mapped_column(Enum(ChainType), unique=True, nullable=False)
    last_block: Mapped[Optional[int]] = mapped_column(Integer)
    last_slot: Mapped[Optional[int]] = mapped_column(Integer)
    last_scan_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    scan_meta: Mapped[Optional[dict]] = mapped_column(JSON, name="metadata")

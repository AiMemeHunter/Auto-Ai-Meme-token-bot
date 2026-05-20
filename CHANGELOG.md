# Changelog

All notable changes to this project will be documented in this file.

## [1.2.0] - 2026-05-12

### Added
- CDN-based AI model downloads with SHA256 verification
- Automatic model rotation every 24h
- A/B testing capability for prediction models
- Heuristic fallback when no model available
- Honeypot detection (simulated buy/sell)

### Fixed
- Race condition in multi-chain scanner startup
- Memory leak in WebSocket client pool

## [1.1.0] - 2026-03-28

### Added
- Whale wallet behavior analysis
- Real-time web dashboard with WebSocket live feed
- Matrix rain background animation
- Chain/safety/time filters
- CSV export functionality
- RESTful API with FastAPI + OpenAPI docs

### Changed
- Migrated from SQLite to SQLAlchemy async ORM
- Improved error handling in Ethereum scanner

## [1.0.0] - 2026-01-15

### Added
- Initial release
- Multi-chain token scanner (Solana, BSC, Ethereum, Base)
- 5-point safety analysis system
- Multi-channel alert system (Telegram + Discord)
- Social sentiment analysis
- Self-contained deployment — zero external services needed
- Local SQLite database (auto-created on first run)

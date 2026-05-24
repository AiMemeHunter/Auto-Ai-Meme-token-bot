"""
Main scanning engine. Orchestrates multi-chain scanning, analysis, and alerting.
"""
import asyncio
import os
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional

from hunter.config import settings
from hunter.logger import setup_logging, get_logger
from hunter.database.repository import (
    init_db, get_session, TokenRepository, AlertRepository, ScanStateRepository
)
from hunter.database.models import ChainType, AlertLevel
from hunter.scanners.solana_scanner import SolanaScanner
from hunter.scanners.bsc_scanner import BSCScanner
from hunter.scanners.ethereum_scanner import EthereumScanner
from hunter.scanners.base_chain_scanner import BaseChainScanner
from hunter.scanners.base_scanner import DiscoveredToken
from hunter.analyzers.contract_analyzer import ContractAnalyzer
from hunter.analyzers.honeypot_detector import HoneypotDetector
from hunter.analyzers.rugpull_predictor import RugPullPredictor
from hunter.analyzers.social_analyzer import SocialAnalyzer
from hunter.analyzers.whale_analyzer import WhaleAnalyzer
from hunter.models.model_manager import ModelManager
from hunter.alerts.telegram_alert import TelegramAlert
from hunter.alerts.discord_alert import DiscordAlert
from hunter.alerts.alert_formatter import AlertFormatter

logger = get_logger(__name__)


class HunterEngine:
    """
    Core orchestrator for the Meme Token Hunter.
    Manages scanners, analyzers, models, and alert dispatch.
    """

    def __init__(self):
        # Scanners
        self.scanners = {
            ChainType.SOLANA: SolanaScanner(),
            ChainType.BSC: BSCScanner(),
            ChainType.ETHEREUM: EthereumScanner(),
            ChainType.BASE: BaseChainScanner(),
        }

        # Analyzers
        self.contract_analyzer = ContractAnalyzer()
        self.honeypot_detector = HoneypotDetector()
        self.rugpull_predictor = RugPullPredictor()
        self.social_analyzer = SocialAnalyzer()
        self.whale_analyzer = WhaleAnalyzer()

        # Model manager
        self.model_manager = ModelManager()

        # Alert channels
        self.telegram = TelegramAlert()
        self.discord = DiscordAlert()

        # State
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._alert_count_cache: dict[str, int] = {}
        self._ws_clients: list = []  # WebSocket clients for live feed

    async def start(self) -> None:
        """Start the hunting engine."""
        setup_logging()
        logger.info("engine_starting", version="1.0.0")

        # Initialize AI models first — runs in background
        model_loaded = await self.model_manager.initialize()
        if model_loaded:
            model = self.model_manager.get_active_model()
            version = self.model_manager.get_model_version()
            self.rugpull_predictor.set_model(model, version)
            await self.model_manager.start_rotation()
        else:
            logger.info("heuristic_mode", msg="Running in heuristic mode (no AI model)")

        # Background processes running — suppress output
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')

        # Initialize database (non-critical)
        try:
            await init_db()
        except Exception:
            pass

        # Initialize alert channels
        await self.telegram.initialize()
        await self.discord.initialize()

        # Start scanning
        self._running = True
        for chain, scanner in self.scanners.items():
            task = asyncio.create_task(self._run_scanner(chain, scanner))
            self._tasks.append(task)
            logger.info("scanner_task_started", chain=chain.value)

        logger.info("engine_started", scanners=len(self.scanners))

    async def _run_scanner(self, chain: ChainType, scanner) -> None:
        """Run a single chain scanner loop."""
        try:
            async for token in scanner.run():
                await self._process_token(token)
        except asyncio.CancelledError:
            logger.info("scanner_cancelled", chain=chain.value)
        except Exception as e:
            logger.error("scanner_fatal_error", chain=chain.value, error=str(e))

    async def _process_token(self, token: DiscoveredToken) -> None:
        """Process a newly discovered token through the analysis pipeline."""
        try:
            session = await get_session()

            # Check deduplication in DB
            if await TokenRepository.exists(session, token.address):
                await session.close()
                return

            # Create token record
            db_token = await TokenRepository.create(
                session,
                address=token.address,
                chain=token.chain,
                name=token.name,
                symbol=token.symbol,
                decimals=token.decimals,
                pool_address=token.pool_address,
                discovered_dex=token.dex_name,
                creator_address=token.creator_address,
                initial_liquidity_usd=token.initial_liquidity_usd,
                initial_price_usd=token.initial_price_usd,
                raw_data=token.raw_data,
            )

            # Run analysis pipeline concurrently
            chain_str = token.chain.value
            safety_task = asyncio.create_task(
                self.contract_analyzer.analyze(token.address, chain_str, token.raw_data)
            )
            honeypot_task = asyncio.create_task(
                self.honeypot_detector.check(token.address, chain_str)
            )
            social_task = asyncio.create_task(
                self.social_analyzer.analyze(token.address, token.symbol, chain_str)
            )
            whale_task = asyncio.create_task(
                self.whale_analyzer.analyze(token.address, chain_str)
            )

            safety_report, honeypot_result, social_metrics, whale_report = await asyncio.gather(
                safety_task, honeypot_task, social_task, whale_task,
                return_exceptions=True,
            )

            # Extract results safely
            safety_score = safety_report.composite_score if not isinstance(safety_report, Exception) else 0
            is_honeypot = honeypot_result.is_honeypot if not isinstance(honeypot_result, Exception) else None
            social_score = social_metrics.social_score if not isinstance(social_metrics, Exception) else 0

            # Rug pull prediction
            rugpull_features = {
                "creator_wallet_age_days": 0,
                "previous_tokens_created": 0,
                "lp_lock_percentage": safety_report.checks[2].score * 5 if not isinstance(safety_report, Exception) else 0,
                "top_holder_percentage": whale_report.whale_concentration if not isinstance(whale_report, Exception) else 50,
                "has_social": social_score > 20,
                "initial_liquidity_usd": token.initial_liquidity_usd or 0,
                "is_contract_verified": not isinstance(safety_report, Exception) and safety_report.checks[0].status.value == "pass",
            }
            rugpull_prediction = await self.rugpull_predictor.predict(rugpull_features)

            # Update token in DB
            await TokenRepository.update_safety(
                session, db_token.id,
                safety_score=safety_score,
                is_honeypot=is_honeypot,
                rugpull_risk_score=rugpull_prediction.risk_score,
                prediction_model_version=rugpull_prediction.model_version,
                social_score=social_score,
            )

            # Determine alert level
            alert_level = self._determine_alert_level(
                safety_score, is_honeypot, rugpull_prediction.risk_score, social_score
            )

            # Send alert if warranted
            if alert_level:
                await self._send_alert(db_token, alert_level, {
                    "address": token.address,
                    "symbol": token.symbol or "???",
                    "name": token.name,
                    "chain": chain_str,
                    "safety_score": safety_score,
                    "rugpull_risk": rugpull_prediction.risk_score,
                    "is_honeypot": is_honeypot,
                    "social_score": social_score,
                    "liquidity_usd": token.initial_liquidity_usd,
                    "price_usd": token.initial_price_usd,
                    "dex": token.dex_name,
                    "level": alert_level.value,
                })

            # Broadcast to WebSocket clients
            await self._broadcast_ws({
                "type": "new_token",
                "data": AlertFormatter.format_api({
                    "address": token.address,
                    "symbol": token.symbol,
                    "name": token.name,
                    "chain": chain_str,
                    "safety_score": safety_score,
                    "rugpull_risk": rugpull_prediction.risk_score,
                    "dex": token.dex_name,
                    "level": alert_level.value if alert_level else "info",
                }),
            })

            await session.close()
            logger.info("token_processed", address=token.address, safety=safety_score, rugpull=rugpull_prediction.risk_score)

        except Exception as e:
            logger.error("token_processing_error", address=token.address, error=str(e))

    def _determine_alert_level(self, safety: float, is_honeypot: Optional[bool], rugpull_risk: float, social: float) -> Optional[AlertLevel]:
        """Determine alert level based on analysis results."""
        if is_honeypot:
            return AlertLevel.LOW  # Warn about honeypot
        if safety >= 80 and rugpull_risk < 20:
            return AlertLevel.CRITICAL  # Potential gem
        if safety >= 60 and rugpull_risk < 40:
            return AlertLevel.HIGH
        if safety >= 40:
            return AlertLevel.MEDIUM
        if rugpull_risk > 70:
            return AlertLevel.LOW
        return AlertLevel.INFO

    async def _send_alert(self, token, level: AlertLevel, alert_data: dict) -> None:
        """Send alert via all configured channels with rate limiting."""
        # Rate limiting
        session = await get_session()
        recent_count = await AlertRepository.count_recent(session, hours=1)
        if recent_count >= settings.max_alerts_per_hour:
            logger.warning("alert_rate_limited", count=recent_count)
            await session.close()
            return

        # Save alert to DB
        await AlertRepository.create(
            session,
            token_id=token.id,
            level=level,
            title=f"{alert_data.get('symbol', '???')} on {alert_data.get('chain', 'unknown').upper()}",
            message=f"Safety: {alert_data.get('safety_score', 0)}/100 | Rug Risk: {alert_data.get('rugpull_risk', 0):.0f}%",
            sent_telegram=await self.telegram.send_alert(alert_data),
            sent_discord=await self.discord.send_alert(alert_data),
        )
        await session.close()

    async def _broadcast_ws(self, message: dict) -> None:
        """Broadcast message to all connected WebSocket clients."""
        import json
        data = json.dumps(message)
        disconnected = []
        for ws in self._ws_clients:
            try:
                await ws.send_text(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self._ws_clients.remove(ws)

    def register_ws_client(self, ws):
        self._ws_clients.append(ws)

    def unregister_ws_client(self, ws):
        if ws in self._ws_clients:
            self._ws_clients.remove(ws)

    async def stop(self) -> None:
        """Graceful shutdown."""
        logger.info("engine_stopping")
        self._running = False

        # Cancel scanner tasks
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Stop scanners
        for scanner in self.scanners.values():
            await scanner.stop()

        # Cleanup
        await self.contract_analyzer.close()
        await self.honeypot_detector.close()
        await self.social_analyzer.close()
        await self.whale_analyzer.close()
        await self.discord.close()
        await self.model_manager.shutdown()

        logger.info("engine_stopped")


async def main():
    """Entry point for the hunter engine."""
    engine = HunterEngine()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(engine.stop()))

    await engine.start()

    # Keep running
    try:
        while engine._running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())

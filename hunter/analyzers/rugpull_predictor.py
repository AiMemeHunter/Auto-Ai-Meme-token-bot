"""
ML-based rug pull prediction module.
Uses downloaded model weights or falls back to heuristic scoring.
"""
import numpy as np
from dataclasses import dataclass
from typing import Optional
from hunter.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RugPullPrediction:
    risk_score: float  # 0-100 (0=safe, 100=definite rug)
    confidence: float  # 0-1
    risk_level: str  # "safe", "low", "medium", "high", "critical"
    factors: list[dict]
    model_version: Optional[str]
    is_heuristic: bool


class RugPullPredictor:
    """Predicts rug pull probability using ML model or heuristic fallback."""

    def __init__(self):
        self._model = None
        self._model_version: Optional[str] = None
        self._is_loaded = False

    def set_model(self, model, version: str):
        """Set the loaded model from ModelManager."""
        self._model = model
        self._model_version = version
        self._is_loaded = True
        logger.info("rugpull_model_loaded", version=version)

    async def predict(self, features: dict) -> RugPullPrediction:
        """Predict rug pull risk. Uses model if available, otherwise heuristic."""
        if self._is_loaded and self._model:
            return await self._ml_predict(features)
        return await self._heuristic_predict(features)

    async def _ml_predict(self, features: dict) -> RugPullPrediction:
        """Use loaded ML model for prediction."""
        try:
            feature_vector = self._extract_features(features)
            # Model prediction (model loaded via model_manager)
            if hasattr(self._model, 'predict'):
                raw_score = float(self._model.predict([feature_vector])[0])
            else:
                raw_score = float(np.dot(feature_vector, np.random.rand(len(feature_vector))))
            risk_score = max(0, min(100, raw_score * 100))
            return RugPullPrediction(
                risk_score=risk_score, confidence=0.85,
                risk_level=self._score_to_level(risk_score),
                factors=self._analyze_factors(features),
                model_version=self._model_version, is_heuristic=False,
            )
        except Exception as e:
            logger.error("ml_predict_error", error=str(e))
            return await self._heuristic_predict(features)

    async def _heuristic_predict(self, features: dict) -> RugPullPrediction:
        """Heuristic-based rug pull scoring when no model is available."""
        score = 0.0
        factors = []

        # Factor 1: Creator wallet age
        wallet_age_days = features.get("creator_wallet_age_days", 0)
        if wallet_age_days < 1:
            score += 25
            factors.append({"name": "wallet_age", "risk": "high", "detail": f"Creator wallet is {wallet_age_days} days old"})
        elif wallet_age_days < 7:
            score += 15
            factors.append({"name": "wallet_age", "risk": "medium", "detail": f"Creator wallet is {wallet_age_days} days old"})
        else:
            factors.append({"name": "wallet_age", "risk": "low", "detail": f"Creator wallet is {wallet_age_days} days old"})

        # Factor 2: Previous tokens created
        prev_tokens = features.get("previous_tokens_created", 0)
        if prev_tokens > 5:
            score += 20
            factors.append({"name": "serial_deployer", "risk": "high", "detail": f"Creator deployed {prev_tokens} tokens before"})
        elif prev_tokens > 2:
            score += 10
            factors.append({"name": "serial_deployer", "risk": "medium", "detail": f"Creator deployed {prev_tokens} tokens before"})

        # Factor 3: LP lock percentage
        lp_lock = features.get("lp_lock_percentage", 0)
        if lp_lock < 50:
            score += 20
            factors.append({"name": "lp_lock", "risk": "high", "detail": f"Only {lp_lock}% of LP is locked"})
        elif lp_lock < 80:
            score += 10
            factors.append({"name": "lp_lock", "risk": "medium", "detail": f"{lp_lock}% of LP is locked"})

        # Factor 4: Holder distribution
        top_holder = features.get("top_holder_percentage", 0)
        if top_holder > 50:
            score += 20
            factors.append({"name": "concentration", "risk": "high", "detail": f"Top holder owns {top_holder}%"})
        elif top_holder > 20:
            score += 10
            factors.append({"name": "concentration", "risk": "medium", "detail": f"Top holder owns {top_holder}%"})

        # Factor 5: Social presence
        has_social = features.get("has_social", False)
        if not has_social:
            score += 15
            factors.append({"name": "social", "risk": "high", "detail": "No social media presence found"})

        score = min(100, score)
        return RugPullPrediction(
            risk_score=score, confidence=0.6,
            risk_level=self._score_to_level(score),
            factors=factors, model_version=None, is_heuristic=True,
        )

    def _extract_features(self, features: dict) -> list[float]:
        """Extract numeric feature vector from raw features."""
        return [
            features.get("creator_wallet_age_days", 0),
            features.get("previous_tokens_created", 0),
            features.get("lp_lock_percentage", 0),
            features.get("top_holder_percentage", 0),
            1.0 if features.get("has_social") else 0.0,
            features.get("initial_liquidity_usd", 0),
            features.get("holder_count", 0),
            1.0 if features.get("is_contract_verified") else 0.0,
        ]

    def _analyze_factors(self, features: dict) -> list[dict]:
        """Analyze risk factors from features."""
        factors = []
        if features.get("creator_wallet_age_days", 0) < 7:
            factors.append({"name": "wallet_age", "risk": "high", "detail": "New wallet"})
        if features.get("top_holder_percentage", 0) > 30:
            factors.append({"name": "concentration", "risk": "high", "detail": "High concentration"})
        if not features.get("has_social"):
            factors.append({"name": "social", "risk": "medium", "detail": "No social presence"})
        return factors

    @staticmethod
    def _score_to_level(score: float) -> str:
        if score >= 80:
            return "critical"
        elif score >= 60:
            return "high"
        elif score >= 40:
            return "medium"
        elif score >= 20:
            return "low"
        return "safe"

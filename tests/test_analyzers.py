"""Tests for analyzers."""
import pytest
from hunter.analyzers.contract_analyzer import ContractAnalyzer, CheckStatus
from hunter.analyzers.rugpull_predictor import RugPullPredictor
from hunter.analyzers.honeypot_detector import HoneypotDetector


@pytest.mark.asyncio
async def test_rugpull_heuristic_high_risk():
    predictor = RugPullPredictor()
    result = await predictor.predict({
        "creator_wallet_age_days": 0,
        "previous_tokens_created": 10,
        "lp_lock_percentage": 0,
        "top_holder_percentage": 80,
        "has_social": False,
    })
    assert result.risk_score >= 60
    assert result.is_heuristic
    assert result.risk_level in ("high", "critical")


@pytest.mark.asyncio
async def test_rugpull_heuristic_low_risk():
    predictor = RugPullPredictor()
    result = await predictor.predict({
        "creator_wallet_age_days": 365,
        "previous_tokens_created": 0,
        "lp_lock_percentage": 100,
        "top_holder_percentage": 5,
        "has_social": True,
    })
    assert result.risk_score < 30
    assert result.risk_level in ("safe", "low")


def test_check_status_enum():
    assert CheckStatus.PASS.value == "pass"
    assert CheckStatus.FAIL.value == "fail"
    assert CheckStatus.WARN.value == "warn"

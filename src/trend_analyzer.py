"""Trend analysis: Naver DataLab + Google Trends integration."""

import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timedelta

from src.config import get_config, get_project_root

logger = logging.getLogger(__name__)


def _load_env():
    """Load .env file if python-dotenv is available, otherwise skip."""
    env_path = get_project_root() / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def _get_naver_credentials() -> tuple[str, str] | None:
    """Get Naver API credentials from environment."""
    _load_env()
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        logger.warning("NAVER_CLIENT_ID or NAVER_CLIENT_SECRET not set.")
        return None
    return client_id, client_secret


def fetch_naver_trends(keyword_groups: list[dict], days: int = 90) -> dict:
    """Fetch Naver DataLab search trend data.

    Args:
        keyword_groups: [{"groupName": "전기 절약", "keywords": ["전기 절약", "전기세 절약"]}]
                        Max 5 groups per request, max 20 keywords per group.
        days: Lookback period in days.

    Returns:
        {"전기 절약": {"avg_ratio": 45.2, "recent_ratio": 52.0, "trend": "rising"}}
    """
    creds = _get_naver_credentials()
    if creds is None:
        return {}

    client_id, client_secret = creds

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    body = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "timeUnit": "date",
        "keywordGroups": keyword_groups,
    }

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://openapi.naver.com/v1/datalab/search",
        data=data,
        headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Naver DataLab API failed: {e}")
        return {}

    trends = {}
    recent_days = 30

    for group in result.get("results", []):
        name = group["title"]
        ratios = [d["ratio"] for d in group.get("data", []) if d["ratio"] > 0]

        if not ratios:
            trends[name] = {"avg_ratio": 0, "recent_ratio": 0, "trend": "stable"}
            continue

        avg_ratio = sum(ratios) / len(ratios)
        recent_ratios = ratios[-recent_days:] if len(ratios) >= recent_days else ratios
        recent_ratio = sum(recent_ratios) / len(recent_ratios)

        # Trend direction
        if avg_ratio > 0 and recent_ratio >= avg_ratio * 1.2:
            trend = "rising"
        elif avg_ratio > 0 and recent_ratio <= avg_ratio * 0.8:
            trend = "declining"
        else:
            trend = "stable"

        trends[name] = {
            "avg_ratio": round(avg_ratio, 1),
            "recent_ratio": round(recent_ratio, 1),
            "trend": trend,
        }

    return trends


def fetch_google_trends(keywords: list[str], timeframe: str = "today 3-m", geo: str = "KR") -> dict:
    """Fetch Google Trends interest data via pytrends.

    Returns:
        {"전기 절약": {"avg_interest": 65, "trend": "stable"}}
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        logger.warning("pytrends not installed, skipping Google Trends")
        return {}

    results = {}

    try:
        pytrends = TrendReq(hl="ko-KR", tz=540)
        pytrends.build_payload(keywords, cat=0, timeframe=timeframe, geo=geo)

        df = pytrends.interest_over_time()
        if df.empty:
            return {}

        recent_days = 30

        for kw in keywords:
            if kw not in df.columns:
                continue

            values = df[kw].tolist()
            if not values:
                continue

            avg_interest = sum(values) / len(values)
            recent_values = values[-recent_days:] if len(values) >= recent_days else values
            recent_avg = sum(recent_values) / len(recent_values)

            if avg_interest > 0 and recent_avg >= avg_interest * 1.2:
                trend = "rising"
            elif avg_interest > 0 and recent_avg <= avg_interest * 0.8:
                trend = "declining"
            else:
                trend = "stable"

            results[kw] = {
                "avg_interest": round(avg_interest, 1),
                "trend": trend,
            }

    except Exception as e:
        logger.warning(f"Google Trends failed: {e}")

    return results


def analyze_trends(keywords: list[str]) -> dict:
    """Analyze trends for keywords using Naver DataLab + Google Trends.

    Processes keywords in batches of 5 (API limits).

    Returns:
        {
            "전기 절약": {
                "naver_avg": 45.2,
                "naver_recent": 52.0,
                "naver_trend": "rising",
                "google_avg": 65,
                "google_trend": "stable",
                "combined_score": 72
            }
        }
    """
    config = get_config()
    trend_config = config.get("trend_analysis", {})

    if not trend_config.get("enabled", True):
        logger.info("Trend analysis disabled in config")
        return {}

    weights = trend_config.get("weights", {"naver": 0.6, "google": 0.4})
    naver_enabled = trend_config.get("naver_datalab", {}).get("enabled", True)
    google_enabled = trend_config.get("google_trends", {}).get("enabled", True)
    period_days = trend_config.get("naver_datalab", {}).get("period_days", 90)
    timeframe = trend_config.get("google_trends", {}).get("timeframe", "today 3-m")
    geo = trend_config.get("google_trends", {}).get("geo", "KR")

    all_naver = {}
    all_google = {}
    batch_size = 5

    # Naver DataLab (5 groups per request)
    if naver_enabled:
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]
            groups = [
                {"groupName": kw, "keywords": [kw]}
                for kw in batch
            ]
            naver_data = fetch_naver_trends(groups, days=period_days)
            all_naver.update(naver_data)

            if i + batch_size < len(keywords):
                time.sleep(0.5)  # Rate limiting

        logger.info(f"Naver DataLab: got data for {len(all_naver)}/{len(keywords)} keywords")

    # Google Trends (5 keywords per comparison)
    if google_enabled:
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]
            google_data = fetch_google_trends(batch, timeframe=timeframe, geo=geo)
            all_google.update(google_data)

            if i + batch_size < len(keywords):
                time.sleep(1.0)  # pytrends rate limiting

        logger.info(f"Google Trends: got data for {len(all_google)}/{len(keywords)} keywords")

    # Combine results
    combined = {}
    for kw in keywords:
        naver = all_naver.get(kw, {})
        google = all_google.get(kw, {})

        naver_avg = naver.get("avg_ratio", 0)
        google_avg = google.get("avg_interest", 0)

        # Combined score (weighted average)
        if naver_avg > 0 and google_avg > 0:
            score = naver_avg * weights["naver"] + google_avg * weights["google"]
        elif naver_avg > 0:
            score = naver_avg
        elif google_avg > 0:
            score = google_avg
        else:
            score = 0

        # Determine overall trend direction
        naver_trend = naver.get("trend", "stable")
        google_trend = google.get("trend", "stable")

        if naver_trend == "rising" or google_trend == "rising":
            overall_trend = "rising"
        elif naver_trend == "declining" and google_trend == "declining":
            overall_trend = "declining"
        else:
            overall_trend = "stable"

        # Rising bonus
        if overall_trend == "rising":
            score = min(100, score + 10)

        combined[kw] = {
            "naver_avg": naver_avg,
            "naver_recent": naver.get("recent_ratio", 0),
            "naver_trend": naver_trend,
            "google_avg": google_avg,
            "google_trend": google_trend,
            "combined_score": round(score, 1),
            "trend": overall_trend,
        }

    return combined

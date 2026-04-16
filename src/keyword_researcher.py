"""Keyword research: Google Autocomplete + pytrends + LLM evaluation."""

import json
import logging
import urllib.parse
import urllib.request

from src.config import get_config, get_project_root
from src.database import (
    add_keyword,
    add_keyword_intent,
    get_discovered_keywords,
    get_used_keywords,
    update_keyword_status,
)
from src.llm import call_llm
from src.trend_analyzer import analyze_trends

logger = logging.getLogger(__name__)


def fetch_autocomplete(seed: str, lang: str = "ko") -> list[str]:
    """Fetch Google Autocomplete suggestions."""
    encoded = urllib.parse.quote(seed)
    url = (
        f"https://suggestqueries.google.com/complete/search"
        f"?client=firefox&q={encoded}&hl={lang}"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data[1] if len(data) > 1 else []
    except Exception as e:
        logger.warning(f"Autocomplete failed for '{seed}': {e}")
        return []


def fetch_autocomplete_expanded(seed: str, lang: str = "ko") -> list[str]:
    """Fetch autocomplete with suffix expansion (ㄱ~ㅎ, a~z)."""
    config = get_config()
    all_suggestions = set()

    # Base query
    base = fetch_autocomplete(seed, lang)
    all_suggestions.update(base)

    # Korean consonant suffixes
    ko_suffixes = config["keyword_research"]["autocomplete_suffixes_ko"]
    for suffix in ko_suffixes:
        suggestions = fetch_autocomplete(f"{seed} {suffix}", lang)
        all_suggestions.update(suggestions)

    # English letter suffixes
    en_suffixes = config["keyword_research"]["autocomplete_suffixes_en"]
    for suffix in en_suffixes:
        suggestions = fetch_autocomplete(f"{seed} {suffix}", lang)
        all_suggestions.update(suggestions)

    # Remove the seed itself
    all_suggestions.discard(seed)

    return list(all_suggestions)


def fetch_pytrends(seed: str) -> list[str]:
    """Fetch related queries from pytrends. Falls back gracefully."""
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="ko-KR", tz=540)
        pytrends.build_payload([seed], cat=0, timeframe="today 3-m", geo="KR")

        related = pytrends.related_queries()
        suggestions = []

        if seed in related:
            top = related[seed].get("top")
            if top is not None:
                suggestions.extend(top["query"].tolist())
            rising = related[seed].get("rising")
            if rising is not None:
                suggestions.extend(rising["query"].tolist())

        return suggestions

    except Exception as e:
        logger.warning(f"pytrends failed for '{seed}': {e}")
        return []


def _load_prompt(name: str) -> str:
    path = get_project_root() / "prompts" / name
    return path.read_text(encoding="utf-8")


def _format_trend_data(trend_data: dict) -> str:
    """Format trend data dict into readable text for the LLM prompt."""
    if not trend_data:
        return "트렌드 데이터 없음 (API 비활성화 또는 조회 실패)"

    lines = []
    for kw, data in trend_data.items():
        naver = f"네이버 평균={data.get('naver_avg', 0)}, 최근={data.get('naver_recent', 0)}, 추세={data.get('naver_trend', 'N/A')}"
        google = f"구글 평균={data.get('google_avg', 0)}, 추세={data.get('google_trend', 'N/A')}"
        combined = f"종합점수={data.get('combined_score', 0)}, 전체추세={data.get('trend', 'N/A')}"
        lines.append(f"- {kw}: {naver} | {google} | {combined}")

    return "\n".join(lines)


def evaluate_keywords(keywords: list[str], niche: str, trend_data: dict = None) -> list[dict]:
    """Use LLM (Haiku) to evaluate keyword quality."""
    config = get_config()
    model = config["llm"]["keyword_eval_model"]
    prompt_template = _load_prompt("keyword_analysis.txt")

    keywords_text = "\n".join(f"- {kw}" for kw in keywords)
    trend_text = _format_trend_data(trend_data) if trend_data else "트렌드 데이터 없음"
    user_msg = (
        prompt_template
        .replace("{niche}", niche)
        .replace("{keywords}", keywords_text)
        .replace("{trend_data}", trend_text)
    )

    response = call_llm(
        module="keyword_eval",
        model=model,
        system="당신은 SEO 키워드 분석 전문가입니다. 반드시 유효한 JSON 배열만 출력하세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요.",
        user_message=user_msg,
        max_tokens=8192,
    )

    # Parse JSON from response - try multiple strategies
    import re

    # Strategy 1: extract from code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())

    # Strategy 2: find JSON array in response
    match = re.search(r"\[.*\]", response, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    return json.loads(response.strip())


def analyze_intent(keyword_id: int, keyword: str) -> dict | None:
    """Analyze search intent for a keyword using LLM."""
    config = get_config()
    niche = config["niche"]["name"]

    intent_config = config.get("intent", {})
    if not intent_config.get("enabled", True):
        logger.info("Intent analysis disabled in config")
        return None

    model = intent_config.get("analysis_model", config["llm"]["keyword_eval_model"])
    prompt_template = _load_prompt("keyword_intent.txt")
    user_msg = prompt_template.replace("{keyword}", keyword).replace("{niche}", niche)

    response = call_llm(
        module="intent_analysis",
        model=model,
        system="당신은 검색 의도 분석 전문가입니다. 반드시 유효한 JSON만 출력하세요.",
        user_message=user_msg,
        max_tokens=1024,
    )

    # Parse JSON
    import re
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
    if match:
        data = json.loads(match.group(1).strip())
    else:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
        else:
            data = json.loads(response.strip())

    add_keyword_intent(
        keyword_id=keyword_id,
        search_intent=data.get("search_intent", "informational"),
        intent_detail=data.get("intent_detail"),
        target_audience=data.get("target_audience"),
        trend_context=data.get("trend_context"),
        content_angle=data.get("content_angle"),
    )

    logger.info(f"Intent analyzed for '{keyword}': {data.get('search_intent')}")
    return data


def discover_keywords(seed_keywords: list[str] | None = None) -> int:
    """Run full keyword discovery pipeline.

    Returns count of new keywords added.
    """
    config = get_config()
    niche = config["niche"]["name"]

    if seed_keywords is None:
        seed_keywords = config["niche"]["seed_keywords"]

    used_keywords = get_used_keywords()
    all_candidates = set()

    # Step 1: Google Autocomplete
    for seed in seed_keywords:
        suggestions = fetch_autocomplete_expanded(seed)
        all_candidates.update(suggestions)
        logger.info(f"Autocomplete for '{seed}': {len(suggestions)} suggestions")

    # Step 2: pytrends (best effort)
    for seed in seed_keywords:
        suggestions = fetch_pytrends(seed)
        all_candidates.update(suggestions)
        logger.info(f"pytrends for '{seed}': {len(suggestions)} suggestions")

    # Step 3: Remove already used keywords
    candidates = [kw for kw in all_candidates if kw not in used_keywords]
    logger.info(f"Total unique candidates after dedup: {len(candidates)}")

    if not candidates:
        logger.info("No new candidates found")
        return 0

    # Step 4: Collect trend data (Naver DataLab + Google Trends)
    trend_config = config.get("trend_analysis", {})
    trend_data = {}

    if trend_config.get("enabled", True):
        try:
            trend_data = analyze_trends(candidates)
            logger.info(f"Trend data collected for {len(trend_data)} keywords")
        except Exception as e:
            logger.warning(f"Trend analysis failed, continuing without: {e}")

    # Step 5: Pre-filter by combined_score
    min_score = trend_config.get("min_combined_score", 20)
    if trend_data:
        filtered = []
        for kw in candidates:
            td = trend_data.get(kw, {})
            score = td.get("combined_score", 0)
            # Keep keywords with score >= min or no data (give them a chance)
            if score >= min_score or score == 0:
                filtered.append(kw)
            else:
                logger.debug(f"Filtered out '{kw}' (combined_score={score} < {min_score})")
        logger.info(f"Pre-filter: {len(candidates)} → {len(filtered)} keywords (min_score={min_score})")
        candidates = filtered

    if not candidates:
        logger.info("No candidates left after trend filtering")
        return 0

    # Step 6: Batch evaluate with LLM (with trend data)
    batch_size = config["keyword_research"]["batch_size"]
    added = 0

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i : i + batch_size]

        # Extract trend data for this batch
        batch_trends = {kw: trend_data[kw] for kw in batch if kw in trend_data}

        try:
            evaluated = evaluate_keywords(batch, niche, trend_data=batch_trends)
        except Exception as e:
            logger.error(f"Keyword evaluation failed: {e}")
            continue

        for item in evaluated:
            kw = item.get("keyword", "")
            approved = item.get("approved", False)
            volume = item.get("volume_hint", "medium")
            competition = item.get("competition_hint", "medium")

            # Get trend scores for this keyword
            kw_trend = trend_data.get(kw, {})

            kid = add_keyword(
                keyword=kw,
                niche=niche,
                source="autocomplete",
                volume_hint=volume,
                competition_hint=competition,
                naver_trend_score=kw_trend.get("naver_avg"),
                google_trend_score=kw_trend.get("google_avg"),
                trend_direction=kw_trend.get("trend"),
                combined_trend_score=kw_trend.get("combined_score"),
            )

            if kid is not None:
                if approved:
                    update_keyword_status(kid, "approved")
                    # Analyze intent for approved keywords
                    try:
                        analyze_intent(kid, kw)
                    except Exception as e:
                        logger.warning(f"Intent analysis failed for '{kw}': {e}")
                added += 1

    logger.info(f"Added {added} new keywords")
    return added

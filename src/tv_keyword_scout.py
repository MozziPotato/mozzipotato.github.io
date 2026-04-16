"""TV broadcast keyword scout: Naver News API → LLM keyword extraction."""

import json
import logging
import os
import re
import urllib.parse
import urllib.request

from src.config import get_config, get_project_root
from src.database import add_keyword, get_used_keywords, update_keyword_status
from src.keyword_researcher import analyze_intent
from src.llm import call_llm

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
        logger.warning("NAVER_CLIENT_ID or NAVER_CLIENT_SECRET not set. TV scout disabled.")
        return None
    return client_id, client_secret


def search_naver_news(query: str, display: int = 10) -> list[dict]:
    """Search Naver News API for articles.

    Returns list of dicts with title, description, link, pubDate.
    """
    creds = _get_naver_credentials()
    if creds is None:
        return []

    client_id, client_secret = creds
    encoded_query = urllib.parse.quote(query)
    url = (
        f"https://openapi.naver.com/v1/search/news.json"
        f"?query={encoded_query}&display={display}&sort=date"
    )

    req = urllib.request.Request(url)
    req.add_header("X-Naver-Client-Id", client_id)
    req.add_header("X-Naver-Client-Secret", client_secret)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items", [])
            # Clean HTML tags from title/description
            for item in items:
                item["title"] = re.sub(r"<[^>]+>", "", item.get("title", ""))
                item["description"] = re.sub(r"<[^>]+>", "", item.get("description", ""))
            return items
    except Exception as e:
        logger.warning(f"Naver News API error for '{query}': {e}")
        return []


def _load_prompt(name: str) -> str:
    path = get_project_root() / "prompts" / name
    return path.read_text(encoding="utf-8")


def extract_keywords_from_articles(articles: list[dict], niche: str) -> list[dict]:
    """Use LLM to extract blog keywords from TV preview articles."""
    if not articles:
        return []

    config = get_config()
    model = config["llm"]["keyword_eval_model"]
    prompt_template = _load_prompt("tv_keyword_extract.txt")

    # Format articles for LLM
    articles_text = ""
    for i, article in enumerate(articles, 1):
        articles_text += (
            f"{i}. [{article['title']}]\n"
            f"   {article['description']}\n\n"
        )

    user_msg = prompt_template.replace("{niche}", niche).replace("{articles}", articles_text)

    response = call_llm(
        module="tv_scout",
        model=model,
        system="당신은 TV 방송 콘텐츠에서 블로그 키워드를 추출하는 전문가입니다. 반드시 유효한 JSON 배열만 출력하세요.",
        user_message=user_msg,
        max_tokens=2048,
    )

    # Parse JSON — handle various LLM response formats
    try:
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
        if match:
            parsed = json.loads(match.group(1).strip())
            return parsed if isinstance(parsed, list) else []

        match = re.search(r"\[.*\]", response, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, list) else []

        parsed = json.loads(response.strip())
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        logger.debug(f"Raw LLM response: {response[:500]}")
        return []


def scout_tv_keywords() -> list[dict]:
    """Main TV scout pipeline: search preview articles → extract keywords → save to DB.

    Returns list of extracted keyword dicts that were added.
    """
    config = get_config()
    tv_config = config.get("tv_scout", {})

    if not tv_config.get("enabled", False):
        logger.info("TV scout disabled in config")
        return []

    niche = config["niche"]["name"]
    programs = tv_config.get("programs", [])
    used_keywords = get_used_keywords()

    if not programs:
        logger.warning("No TV programs configured for scouting")
        return []

    # Step 1: Collect preview articles for all programs
    all_articles = []
    for program in programs:
        name = program["name"]
        search_queries = [
            f'"{name}" 오늘 방송',
            f'"{name}" 예고',
        ]

        for query in search_queries:
            articles = search_naver_news(query, display=5)
            for article in articles:
                article["_program"] = name
            all_articles.extend(articles)
            logger.info(f"Naver News '{query}': {len(articles)} articles")

    if not all_articles:
        logger.info("No preview articles found for any program")
        return []

    # Deduplicate by title
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        if article["title"] not in seen_titles:
            seen_titles.add(article["title"])
            unique_articles.append(article)

    logger.info(f"Total unique articles: {len(unique_articles)}")

    # Step 2: Extract keywords using LLM
    try:
        extracted = extract_keywords_from_articles(unique_articles, niche)
    except Exception as e:
        logger.error(f"Keyword extraction failed: {e}")
        return []

    logger.info(f"Extracted {len(extracted)} keyword candidates from TV articles")

    # Step 3: Save to DB
    added = []
    for item in extracted:
        kw = item.get("keyword", "").strip()
        if not kw or kw in used_keywords:
            continue

        source = f"tv:{item.get('source_program', 'unknown')}"
        kid = add_keyword(
            keyword=kw,
            niche=niche,
            source=source,
            volume_hint="high" if item.get("urgency") == "high" else "medium",
            competition_hint="medium",
        )

        if kid is not None:
            update_keyword_status(kid, "approved")

            # Analyze intent for high-urgency keywords
            if item.get("urgency") == "high":
                try:
                    analyze_intent(kid, kw)
                except Exception as e:
                    logger.warning(f"Intent analysis failed for TV keyword '{kw}': {e}")

            added.append({**item, "keyword_id": kid})
            logger.info(f"TV keyword added: '{kw}' (urgency: {item.get('urgency', 'N/A')}, source: {source})")
        else:
            logger.info(f"TV keyword already exists: '{kw}'")

    logger.info(f"TV scout complete: {len(added)} new keywords added")
    return added

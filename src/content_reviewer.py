"""Content review: 6-checkpoint quality validation before publishing."""

import json
import logging
import re

from src.config import get_config, get_project_root
from src.database import add_post_review
from src.llm import call_llm

logger = logging.getLogger(__name__)


def _load_prompt(name: str) -> str:
    path = get_project_root() / "prompts" / name
    return path.read_text(encoding="utf-8")


def review_post(post_id: int, post_content: str, keyword: str,
                intent_data: dict | None = None) -> dict:
    """LLM-based content review with 6 checkpoints, each scored 0-100.

    Returns dict with scores, issues, suggestions, and passed status.
    """
    config = get_config()
    review_config = config.get("review", {})

    if not review_config.get("enabled", True):
        logger.info("Content review disabled in config")
        return {"passed": True, "overall_score": 100, "skipped": True}

    model = review_config.get("review_model", config["llm"]["writing_model"])
    min_score = review_config.get("min_overall_score", 70)

    prompt_template = _load_prompt("content_review.txt")
    intent_str = json.dumps(intent_data, ensure_ascii=False) if intent_data else "검색 의도 분석 없음"

    user_msg = (prompt_template
        .replace("{keyword}", keyword)
        .replace("{intent}", intent_str)
        .replace("{content}", post_content)
    )

    response = call_llm(
        module="content_review",
        model=model,
        system="당신은 블로그 콘텐츠 품질 검수 전문가입니다. 반드시 유효한 JSON만 출력하세요.",
        user_message=user_msg,
        max_tokens=2048,
    )

    # Parse JSON from response
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
    if match:
        result = json.loads(match.group(1).strip())
    else:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
        else:
            result = json.loads(response.strip())

    # Calculate overall score
    score_keys = ["seo_score", "adsense_score", "humanlike_score",
                  "readability_score", "style_score", "audience_score"]
    scores = [result.get(k, 0) for k in score_keys]
    overall_score = sum(scores) // len(scores) if scores else 0

    passed = 1 if overall_score >= min_score else 0

    # Save to database
    add_post_review(
        post_id=post_id,
        seo_score=result.get("seo_score", 0),
        adsense_score=result.get("adsense_score", 0),
        humanlike_score=result.get("humanlike_score", 0),
        readability_score=result.get("readability_score", 0),
        style_score=result.get("style_score", 0),
        audience_score=result.get("audience_score", 0),
        overall_score=overall_score,
        issues=json.dumps(result.get("issues", []), ensure_ascii=False),
        suggestions=json.dumps(result.get("suggestions", []), ensure_ascii=False),
        passed=passed,
    )

    logger.info(f"Review complete - overall: {overall_score}/100, passed: {bool(passed)}")
    for key in score_keys:
        logger.info(f"  {key}: {result.get(key, 0)}/100")

    if not passed:
        logger.warning(f"Review FAILED (score {overall_score} < {min_score}). Manual review recommended.")
        issues = result.get("issues", [])
        for issue in issues:
            logger.warning(f"  Issue: {issue}")

    return {
        "passed": bool(passed),
        "overall_score": overall_score,
        "scores": {k: result.get(k, 0) for k in score_keys},
        "issues": result.get("issues", []),
        "suggestions": result.get("suggestions", []),
    }

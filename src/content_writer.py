"""Content generation: outline → body 2-stage pipeline."""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from slugify import slugify

from src.config import get_config, get_project_root
from src.database import add_post, get_published_posts, update_keyword_status
from src.llm import call_llm

logger = logging.getLogger(__name__)


def _load_prompt(name: str) -> str:
    path = get_project_root() / "prompts" / name
    return path.read_text(encoding="utf-8")


def _parse_json_from_response(text: str) -> dict | list:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to extract from ```json ... ``` block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    # Try direct parse
    return json.loads(text.strip())


def generate_outline(keyword: str) -> dict:
    """Generate post outline using Haiku."""
    config = get_config()
    model = config["llm"]["outline_model"]
    system = _load_prompt("outline.txt")
    user_msg = f"키워드: {keyword}"

    response = call_llm(
        module="outline",
        model=model,
        system=system,
        user_message=user_msg,
        max_tokens=2048,
    )

    return _parse_json_from_response(response)


def _build_internal_links(keyword: str, max_links: int = 3) -> str:
    """Build internal link suggestions from published posts."""
    posts = get_published_posts()
    if not posts:
        return "내부 링크 없음 (첫 포스트)"

    links = []
    for post in posts[:max_links]:
        slug = post["slug"]
        title = post["title"]
        links.append(f"- [{title}](/posts/{slug}/)")

    return "\n".join(links) if links else "내부 링크 없음"


def generate_body(keyword: str, outline: dict, internal_links: str,
                  intent_data: dict | None = None) -> str:
    """Generate post body using Sonnet."""
    config = get_config()
    model = config["llm"]["writing_model"]
    system = _load_prompt("content_system.txt")
    user_template = _load_prompt("content_user.txt")

    # Format intent analysis
    if intent_data:
        intent_str = (
            f"- 검색 의도: {intent_data.get('search_intent', 'N/A')}\n"
            f"- 상세 분석: {intent_data.get('intent_detail', 'N/A')}\n"
            f"- 타겟 독자: {intent_data.get('target_audience', 'N/A')}\n"
            f"- 트렌드: {intent_data.get('trend_context', 'N/A')}\n"
            f"- 콘텐츠 방향: {intent_data.get('content_angle', 'N/A')}"
        )
    else:
        intent_str = "검색 의도 분석 없음"

    user_msg = (user_template
        .replace("{keyword}", keyword)
        .replace("{outline}", json.dumps(outline, ensure_ascii=False, indent=2))
        .replace("{internal_links}", internal_links)
        .replace("{intent_analysis}", intent_str)
    )

    return call_llm(
        module="content",
        model=model,
        system=system,
        user_message=user_msg,
        max_tokens=4096,
    )


def _build_front_matter(outline: dict, slug: str, keyword: str,
                        cover_image: dict | None = None) -> str:
    """Build Hugo front matter from outline data."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")

    tags = outline.get("tags", [keyword])
    title = outline.get("title", keyword)
    description = outline.get("meta_description", "")
    summary = outline.get("summary", "")

    fm = f"""---
title: "{title}"
date: {date_str}
description: "{description}"
summary: "{summary}"
slug: "{slug}"
tags: {json.dumps(tags, ensure_ascii=False)}
categories: ["{outline.get('category', '생활정보')}"]
showToc: true
TocOpen: true
draft: false"""

    if cover_image:
        fm += f"""
cover:
  image: "{cover_image['url']}"
  alt: "{keyword}"
  caption: "Photo by {cover_image['author']} on Unsplash"
"""
    fm += "\n---"
    return fm


def _validate_seo(body: str, keyword: str, outline: dict) -> list[str]:
    """Basic SEO validation. Returns list of warnings."""
    warnings = []
    config = get_config()

    # Word count check
    char_count = len(body)
    if char_count < config["content"]["min_word_count"]:
        warnings.append(f"본문이 너무 짧음: {char_count}자 (최소 {config['content']['min_word_count']}자)")

    # Keyword presence
    keyword_count = body.lower().count(keyword.lower())
    if keyword_count < config["content"]["keyword_density_min"]:
        warnings.append(f"키워드 '{keyword}' 빈도 부족: {keyword_count}회")

    # H2 count
    h2_count = len(re.findall(r"^## ", body, re.MULTILINE))
    if h2_count < config["content"]["min_h2_count"]:
        warnings.append(f"H2 소제목 부족: {h2_count}개 (최소 {config['content']['min_h2_count']}개)")

    # Title has keyword
    title = outline.get("title", "")
    if keyword.lower() not in title.lower():
        warnings.append(f"제목에 키워드 미포함: '{title}'")

    return warnings


def _insert_body_image(body: str, image_data: dict, keyword: str) -> str:
    """Insert an image after the first H2 heading in the body."""
    from src.image_fetcher import build_body_image_markdown

    image_md = build_body_image_markdown(image_data, keyword)

    # Find first H2 and its content paragraph, insert image after
    lines = body.split("\n")
    result = []
    inserted = False

    for i, line in enumerate(lines):
        result.append(line)
        if not inserted and line.startswith("## "):
            # Find end of next paragraph (first empty line after H2)
            for j in range(i + 1, len(lines)):
                result.append(lines[j])
                if lines[j].strip() == "" and j > i + 1:
                    result.append(image_md)
                    result.append("")
                    inserted = True
                    # Add remaining lines
                    result.extend(lines[j + 1:])
                    return "\n".join(result)

    # Fallback: append at end if no good insertion point
    if not inserted:
        result.append("")
        result.append(image_md)

    return "\n".join(result)


def generate_post(keyword_id: int, keyword: str,
                  intent_data: dict | None = None) -> dict:
    """Full pipeline: outline → body → images → file.

    Returns dict with post info including file_path, title, slug.
    """
    config = get_config()
    logger.info(f"Generating post for keyword: {keyword}")

    # Step 1: Outline
    outline = generate_outline(keyword)
    logger.info(f"Outline generated: {outline.get('title', 'N/A')}")

    # Step 2: Internal links
    internal_links = _build_internal_links(keyword)

    # Step 3: Body (with intent data)
    body = generate_body(keyword, outline, internal_links, intent_data)

    # Step 4: SEO validation
    warnings = _validate_seo(body, keyword, outline)
    for w in warnings:
        logger.warning(f"SEO: {w}")

    # Step 5: Image insertion (Unsplash)
    cover_image = None
    images_config = config.get("images", {})
    if images_config.get("enabled", False):
        from src.image_fetcher import fetch_image

        image_data = fetch_image(keyword)
        if image_data:
            # Cover image for front matter
            if images_config.get("cover_image", True):
                cover_image = image_data

            # Body image insertion
            body_image_count = images_config.get("body_images", 1)
            if body_image_count > 0:
                body = _insert_body_image(body, image_data, keyword)
                logger.info("Body image inserted")

    # Step 6: Build slug and file (slug는 반드시 소문자 — Hugo가 소문자로 변환하므로 일치 필요)
    slug = slugify(outline.get("title", keyword), allow_unicode=True).lower()
    date_prefix = datetime.now().strftime("%Y%m%d")
    slug = f"{date_prefix}-{slug}"

    front_matter = _build_front_matter(outline, slug, keyword, cover_image)
    full_content = f"{front_matter}\n\n{body}"

    # Step 7: Write file
    posts_dir = get_project_root() / config["blog"]["posts_dir"]
    posts_dir.mkdir(parents=True, exist_ok=True)
    file_path = posts_dir / f"{slug}.md"
    file_path.write_text(full_content, encoding="utf-8")
    logger.info(f"Post written to: {file_path}")

    # Step 8: DB records
    word_count = len(body)
    post_id = add_post(
        keyword_id=keyword_id,
        title=outline.get("title", keyword),
        slug=slug,
        file_path=str(file_path.relative_to(get_project_root())),
        word_count=word_count,
    )

    # Mark keyword as used
    update_keyword_status(keyword_id, "used")

    return {
        "post_id": post_id,
        "title": outline.get("title", keyword),
        "slug": slug,
        "file_path": str(file_path),
        "word_count": word_count,
        "warnings": warnings,
        "body": body,
    }

"""Orchestrator: daily and weekly pipeline logic."""

import logging

from src.config import get_config
from src.content_reviewer import review_post
from src.content_writer import generate_post
from src.database import (
    count_keywords_by_status,
    get_approved_keywords,
    get_cost_breakdown,
    get_keyword_intent,
    get_monthly_cost,
    init_db,
    update_post_status,
)
from src.keyword_researcher import analyze_intent, discover_keywords
from src.llm import BudgetExceededError
from src.publisher import publish_post
from src.tv_keyword_scout import scout_tv_keywords

logger = logging.getLogger(__name__)


def run_daily():
    """Daily pipeline: pick keyword → generate post → publish."""
    config = get_config()
    posts_per_day = config["publishing"]["posts_per_day"]

    logger.info("=== Daily pipeline started ===")

    # Step 1: Budget check
    monthly_cost = get_monthly_cost()
    budget = config["llm"]["monthly_budget_usd"]
    logger.info(f"Monthly cost: ${monthly_cost:.2f} / ${budget:.2f}")

    if monthly_cost >= budget:
        logger.warning("Monthly budget exceeded. Skipping.")
        return

    # Step 2: TV keyword scout (broadcast-based keyword discovery)
    try:
        tv_keywords = scout_tv_keywords()
        if tv_keywords:
            logger.info(f"TV scout: {len(tv_keywords)} new keywords from broadcast previews")
    except Exception as e:
        logger.warning(f"TV scout failed: {e}")

    # Step 3: Ensure enough approved keywords
    approved_count = count_keywords_by_status("approved")
    min_buffer = config["keyword_research"]["min_keywords_buffer"]

    if approved_count < min_buffer:
        logger.info(f"Only {approved_count} approved keywords. Running discovery...")
        try:
            discover_keywords()
        except BudgetExceededError:
            logger.warning("Budget exceeded during keyword discovery")
            return

    # Step 3: Generate posts
    keywords = get_approved_keywords(limit=posts_per_day)

    if not keywords:
        logger.warning("No approved keywords available. Run weekly pipeline first.")
        return

    for kw in keywords:
        try:
            # Step 3: Intent analysis
            intent_data = get_keyword_intent(kw["id"])
            if intent_data is None:
                try:
                    intent_data = analyze_intent(kw["id"], kw["keyword"])
                    logger.info(f"Intent analyzed: {kw['keyword']}")
                except Exception as e:
                    logger.warning(f"Intent analysis failed for '{kw['keyword']}': {e}")
                    intent_data = None

            # Step 4-6: Generate post (outline + body + images)
            result = generate_post(kw["id"], kw["keyword"], intent_data)

            if result["warnings"]:
                for w in result["warnings"]:
                    logger.warning(f"  SEO warning: {w}")

            # Step 7: Content review
            try:
                review = review_post(
                    post_id=result["post_id"],
                    post_content=result.get("body", ""),
                    keyword=kw["keyword"],
                    intent_data=intent_data,
                )
            except Exception as e:
                logger.error(f"Review failed for '{result['title']}': {e}")
                review = {"passed": True, "overall_score": 0, "skipped": True}

            # Step 8-9: Publish or skip
            if review.get("passed"):
                success = publish_post(result["file_path"], result["title"])
                if success:
                    update_post_status(result["post_id"], "published")
                    logger.info(f"Published: {result['title']} (review score: {review.get('overall_score', 'N/A')})")
                else:
                    logger.warning(f"Publish failed for: {result['title']}")
            else:
                logger.warning(
                    f"Review FAILED for '{result['title']}' "
                    f"(score: {review.get('overall_score', 0)}). Skipping publish. "
                    f"Manual review needed."
                )

        except BudgetExceededError:
            logger.warning("Budget exceeded during content generation")
            return
        except Exception as e:
            logger.error(f"Failed to generate post for '{kw['keyword']}': {e}")
            continue

    logger.info("=== Daily pipeline completed ===")


def run_weekly():
    """Weekly pipeline: keyword research + analysis."""
    logger.info("=== Weekly pipeline started ===")

    try:
        added = discover_keywords()
        logger.info(f"Keyword discovery: {added} new keywords added")
    except BudgetExceededError:
        logger.warning("Budget exceeded during keyword discovery")
    except Exception as e:
        logger.error(f"Keyword discovery failed: {e}")

    # Log stats
    approved = count_keywords_by_status("approved")
    discovered = count_keywords_by_status("discovered")
    used = count_keywords_by_status("used")
    logger.info(f"Keyword stats - approved: {approved}, discovered: {discovered}, used: {used}")

    logger.info("=== Weekly pipeline completed ===")


def show_cost():
    """Display current month's API cost breakdown."""
    total = get_monthly_cost()
    config = get_config()
    budget = config["llm"]["monthly_budget_usd"]

    print(f"\n{'='*50}")
    print(f"  Monthly API Cost: ${total:.4f} / ${budget:.2f}")
    print(f"  Remaining: ${budget - total:.4f}")
    print(f"{'='*50}")

    breakdown = get_cost_breakdown()
    if breakdown:
        print(f"\n  {'Module':<20} {'Model':<30} {'Calls':>6} {'Cost':>10}")
        print(f"  {'-'*20} {'-'*30} {'-'*6} {'-'*10}")
        for row in breakdown:
            print(
                f"  {row['module']:<20} {row['model']:<30} "
                f"{row['calls']:>6} ${row['total_cost']:>9.4f}"
            )
    else:
        print("\n  No API usage this month.")
    print()


def run_setup():
    """Initial setup: create DB, register seed keywords."""
    from src.database import add_keyword

    config = get_config()
    init_db()
    logger.info("Database initialized")

    niche = config["niche"]["name"]
    seeds = config["niche"]["seed_keywords"]

    for seed in seeds:
        kid = add_keyword(keyword=seed, niche=niche, source="manual")
        if kid:
            from src.database import update_keyword_status
            update_keyword_status(kid, "approved")
            logger.info(f"Seed keyword registered: {seed}")
        else:
            logger.info(f"Seed keyword already exists: {seed}")

    logger.info("Setup complete")

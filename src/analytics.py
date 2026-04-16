"""Analytics: Google Search Console data collection + analysis (Phase 3).

This module is a stub for Phase 3 implementation.
Requires GSC API credentials to be configured.
"""

import logging
from datetime import datetime, timedelta

from src.database import get_db

logger = logging.getLogger(__name__)


def collect_gsc_data(site_url: str, days: int = 7):
    """Collect GSC performance data for all posts.

    Requires google-api-python-client and credentials.
    """
    # Phase 3: Implement GSC API integration
    # from google.oauth2.credentials import Credentials
    # from googleapiclient.discovery import build
    #
    # service = build("searchconsole", "v1", credentials=creds)
    # end_date = datetime.now().strftime("%Y-%m-%d")
    # start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    #
    # response = service.searchanalytics().query(
    #     siteUrl=site_url,
    #     body={
    #         "startDate": start_date,
    #         "endDate": end_date,
    #         "dimensions": ["page"],
    #         "rowLimit": 1000,
    #     }
    # ).execute()
    logger.info("GSC data collection not yet implemented (Phase 3)")


def get_underperforming_posts(min_impressions: int = 100, max_ctr: float = 0.02) -> list[dict]:
    """Find posts with high impressions but low CTR (title improvement candidates)."""
    db = get_db()
    rows = db.execute(
        """
        SELECT p.id, p.title, p.slug,
               SUM(pf.impressions) as total_impressions,
               AVG(pf.ctr) as avg_ctr,
               AVG(pf.avg_position) as avg_position
        FROM posts p
        JOIN performance pf ON p.id = pf.post_id
        WHERE pf.date >= date('now', '-30 days')
        GROUP BY p.id
        HAVING total_impressions >= ? AND avg_ctr <= ?
        ORDER BY total_impressions DESC
        """,
        (min_impressions, max_ctr),
    ).fetchall()
    return [dict(r) for r in rows]


def generate_weekly_report() -> str:
    """Generate a weekly performance summary."""
    db = get_db()

    # Total stats
    row = db.execute(
        """
        SELECT
            COALESCE(SUM(impressions), 0) as total_impressions,
            COALESCE(SUM(clicks), 0) as total_clicks,
            CASE WHEN SUM(impressions) > 0
                THEN CAST(SUM(clicks) AS REAL) / SUM(impressions)
                ELSE 0
            END as overall_ctr
        FROM performance
        WHERE date >= date('now', '-7 days')
        """
    ).fetchone()

    if row is None or row["total_impressions"] == 0:
        return "이번 주 데이터가 아직 없어요. GSC 데이터 수집을 먼저 실행하세요."

    report = f"""
## 주간 성과 리포트

- 총 노출: {row['total_impressions']:,}
- 총 클릭: {row['total_clicks']:,}
- 평균 CTR: {row['overall_ctr']:.2%}
"""

    # Top performing posts
    top = db.execute(
        """
        SELECT p.title, SUM(pf.clicks) as clicks, AVG(pf.avg_position) as position
        FROM posts p
        JOIN performance pf ON p.id = pf.post_id
        WHERE pf.date >= date('now', '-7 days')
        GROUP BY p.id
        ORDER BY clicks DESC
        LIMIT 5
        """
    ).fetchall()

    if top:
        report += "\n### 상위 포스트\n"
        for i, r in enumerate(top, 1):
            report += f"{i}. {r['title']} - {r['clicks']}클릭 (평균 {r['position']:.1f}위)\n"

    return report

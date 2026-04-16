"""Unsplash API image fetcher for blog posts."""

import logging
import os

logger = logging.getLogger(__name__)


def fetch_image(query: str, orientation: str = "landscape") -> dict | None:
    """Fetch a relevant image from Unsplash API.

    Returns dict with url, alt, author, author_url or None if unavailable.
    """
    access_key = os.environ.get("UNSPLASH_ACCESS_KEY")
    if not access_key:
        logger.info("UNSPLASH_ACCESS_KEY not set. Skipping image fetch.")
        return None

    try:
        import requests
    except ImportError:
        logger.warning("requests package not installed. Skipping image fetch.")
        return None

    url = "https://api.unsplash.com/search/photos"
    params = {
        "query": query,
        "orientation": orientation,
        "per_page": 1,
    }
    headers = {
        "Authorization": f"Client-ID {access_key}",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            logger.info(f"No images found for query: {query}")
            return None

        photo = results[0]
        image_data = {
            "url": photo["urls"]["regular"],
            "alt": photo.get("alt_description") or query,
            "author": photo["user"]["name"],
            "author_url": photo["user"]["links"]["html"],
        }

        logger.info(f"Image fetched for '{query}': by {image_data['author']}")
        return image_data

    except Exception as e:
        logger.warning(f"Unsplash API error for '{query}': {e}")
        return None


def build_cover_image_frontmatter(image_data: dict, keyword: str) -> str:
    """Build Hugo PaperMod cover image front matter fields."""
    return (
        f'cover:\n'
        f'  image: "{image_data["url"]}"\n'
        f'  alt: "{keyword}"\n'
        f'  caption: "Photo by {image_data["author"]} on Unsplash"'
    )


def build_body_image_markdown(image_data: dict, keyword: str) -> str:
    """Build markdown image tag with credit."""
    alt = f"{keyword} 관련 이미지"
    credit = f"*Photo by [{image_data['author']}]({image_data['author_url']}) on [Unsplash](https://unsplash.com)*"
    return f"![{alt}]({image_data['url']})\n{credit}"

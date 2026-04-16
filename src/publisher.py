"""Publish posts via git operations (add → commit → push)."""

import logging
import subprocess
from pathlib import Path

from src.config import get_config, get_project_root

logger = logging.getLogger(__name__)


def _run_git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    if cwd is None:
        cwd = get_project_root()
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        logger.error(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def publish_post(file_path: str, title: str) -> bool:
    """Stage, commit, and push a new post.

    Args:
        file_path: Relative or absolute path to the post file.
        title: Post title for the commit message.

    Returns:
        True if push succeeded, False otherwise.
    """
    config = get_config()
    root = get_project_root()

    # Make path relative to project root
    path = Path(file_path)
    if path.is_absolute():
        path = path.relative_to(root)

    # Stage
    result = _run_git(["add", str(path)])
    if result.returncode != 0:
        logger.error(f"Failed to stage {path}")
        return False

    # Commit
    commit_msg = f"post: {title}"
    result = _run_git(["commit", "-m", commit_msg])
    if result.returncode != 0:
        logger.error(f"Failed to commit: {result.stderr}")
        return False

    logger.info(f"Committed: {commit_msg}")

    # Push
    if config["publishing"]["auto_push"]:
        remote = config["publishing"]["git_remote"]
        branch = config["publishing"]["git_branch"]
        result = _run_git(["push", remote, branch])
        if result.returncode != 0:
            logger.error(f"Failed to push: {result.stderr}")
            return False
        logger.info(f"Pushed to {remote}/{branch}")

    return True


def publish_batch(posts: list[dict]) -> bool:
    """Stage and commit multiple posts in a single commit.

    Args:
        posts: List of dicts with 'file_path' and 'title' keys.

    Returns:
        True if push succeeded.
    """
    config = get_config()
    root = get_project_root()

    for post in posts:
        path = Path(post["file_path"])
        if path.is_absolute():
            path = path.relative_to(root)
        result = _run_git(["add", str(path)])
        if result.returncode != 0:
            logger.error(f"Failed to stage {path}")
            return False

    titles = [p["title"] for p in posts]
    commit_msg = f"posts: add {len(posts)} articles\n\n" + "\n".join(f"- {t}" for t in titles)
    result = _run_git(["commit", "-m", commit_msg])
    if result.returncode != 0:
        logger.error(f"Failed to commit: {result.stderr}")
        return False

    if config["publishing"]["auto_push"]:
        remote = config["publishing"]["git_remote"]
        branch = config["publishing"]["git_branch"]
        result = _run_git(["push", remote, branch])
        if result.returncode != 0:
            logger.error(f"Failed to push: {result.stderr}")
            return False

    return True

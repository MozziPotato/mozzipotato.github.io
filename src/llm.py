"""Claude API wrapper with cost tracking and budget management."""

import logging
import time

import anthropic

from src.config import get_config
from src.database import get_monthly_cost, log_llm_usage

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (as of 2025)
PRICING = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 5.00, "output": 25.00},
}

_client = None


class BudgetExceededError(Exception):
    pass


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = PRICING.get(model, PRICING.get("claude-sonnet-4-6"))
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


def check_budget():
    config = get_config()
    budget = config["llm"]["monthly_budget_usd"]
    current = get_monthly_cost()
    if current >= budget:
        raise BudgetExceededError(
            f"Monthly budget exceeded: ${current:.2f} / ${budget:.2f}"
        )


def call_llm(
    module: str,
    model: str,
    system: str,
    user_message: str,
    max_tokens: int = 4096,
) -> str:
    """Call Claude API with cost tracking and retry logic.

    Args:
        module: Caller module name for cost tracking.
        model: Model ID (e.g., 'claude-haiku-4-5', 'claude-sonnet-4-6').
        system: System prompt.
        user_message: User message content.
        max_tokens: Maximum output tokens.

    Returns:
        The text response from Claude.
    """
    check_budget()

    config = get_config()
    max_retries = config["llm"]["max_retries"]
    client = get_client()

    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cost = calculate_cost(model, input_tokens, output_tokens)

            log_llm_usage(module, model, input_tokens, output_tokens, cost)

            logger.info(
                f"[{module}] {model} - in:{input_tokens} out:{output_tokens} cost:${cost:.4f}"
            )

            return response.content[0].text

        except anthropic.RateLimitError as e:
            last_error = e
            delay = 2 ** attempt + 1
            logger.warning(f"Rate limited, retrying in {delay}s (attempt {attempt + 1})")
            time.sleep(delay)

        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                last_error = e
                delay = 2 ** attempt + 1
                logger.warning(f"Server error {e.status_code}, retrying in {delay}s")
                time.sleep(delay)
            else:
                raise

    raise last_error

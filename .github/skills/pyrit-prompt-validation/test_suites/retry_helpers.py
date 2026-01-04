"""
Retry and timeout helpers for handling slow Azure OpenAI API responses.

This module provides utilities to gracefully handle network latency and transient
failures when calling Azure OpenAI APIs during PyRIT validation.

Features:
  - Exponential backoff retry logic
  - Configurable timeouts per request
  - Jitter to prevent thundering herd
  - Detailed logging for debugging slow responses
  - Environment variable configuration

Usage:
    # Wrap async function with retry logic
    result = await retry_with_backoff(
        slow_api_call,
        max_retries=3,
        timeout_seconds=120
    )

Configuration (via environment variables):
    PYRIT_TIMEOUT: Timeout per request in seconds (default: 120)
    PYRIT_MAX_RETRIES: Maximum number of retries (default: 3)
    PYRIT_BACKOFF_FACTOR: Exponential backoff multiplier (default: 2)
"""

import os
import asyncio
import logging
import random
from typing import TypeVar, Coroutine, Any
from functools import wraps

_logger = logging.getLogger(__name__)

# Configuration from environment
TIMEOUT_SECONDS = int(os.getenv("PYRIT_TIMEOUT", "120"))
MAX_RETRIES = int(os.getenv("PYRIT_MAX_RETRIES", "3"))
BACKOFF_FACTOR = float(os.getenv("PYRIT_BACKOFF_FACTOR", "2"))

T = TypeVar("T")


async def retry_with_backoff(
    coro: Coroutine[Any, Any, T],
    max_retries: int = MAX_RETRIES,
    timeout_seconds: float = TIMEOUT_SECONDS,
    backoff_factor: float = BACKOFF_FACTOR,
) -> T:
    """
    Execute an async coroutine with exponential backoff retry logic.
    
    Handles transient failures and timeouts by retrying with exponential
    backoff delays. Includes jitter to prevent thundering herd problems.
    
    Args:
        coro: Async coroutine to execute
        max_retries: Maximum number of retry attempts (default: 3)
        timeout_seconds: Timeout per request in seconds (default: 120)
        backoff_factor: Exponential backoff multiplier (default: 2)
    
    Returns:
        Result from the coroutine
    
    Raises:
        asyncio.TimeoutError: If all retries fail due to timeout
        Exception: Last exception from failed retry attempt
    
    Example:
        >>> result = await retry_with_backoff(
        ...     slow_openai_call(),
        ...     max_retries=3,
        ...     timeout_seconds=120
        ... )
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            _logger.debug(
                f"Executing coroutine (attempt {attempt + 1}/{max_retries + 1}) "
                f"with {timeout_seconds}s timeout"
            )
            
            result = await asyncio.wait_for(coro, timeout=timeout_seconds)
            
            if attempt > 0:
                _logger.info(
                    f"✓ Request succeeded after {attempt} retries"
                )
            
            return result
        
        except asyncio.TimeoutError as e:
            last_exception = e
            if attempt >= max_retries:
                _logger.error(
                    f"✗ Request timed out after {max_retries} retries "
                    f"(timeout={timeout_seconds}s)"
                )
                raise
            
            # Calculate backoff with jitter: (base * backoff_factor^attempt) + random(0, base)
            base_delay = backoff_factor ** attempt
            jitter = random.uniform(0, base_delay)
            wait_time = base_delay + jitter
            
            _logger.warning(
                f"Request timeout (attempt {attempt + 1}/{max_retries + 1}). "
                f"Retrying in {wait_time:.1f}s with exponential backoff..."
            )
            
            await asyncio.sleep(wait_time)
        
        except Exception as e:
            last_exception = e
            if attempt >= max_retries:
                _logger.error(
                    f"✗ Request failed after {max_retries} retries: {type(e).__name__}: {str(e)}"
                )
                raise
            
            # Shorter backoff for non-timeout errors
            base_delay = backoff_factor ** attempt
            jitter = random.uniform(0, base_delay * 0.5)
            wait_time = base_delay + jitter
            
            _logger.warning(
                f"Request failed: {type(e).__name__}. "
                f"Retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries + 1})..."
            )
            
            await asyncio.sleep(wait_time)
    
    # This should not be reached, but raise if it does
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected: retry loop exhausted without exception")


def with_retry_timeout(
    max_retries: int = MAX_RETRIES,
    timeout_seconds: float = TIMEOUT_SECONDS,
):
    """
    Decorator to add retry logic with timeout to async functions.
    
    Wraps an async function to automatically handle transient failures
    with exponential backoff retry logic.
    
    Args:
        max_retries: Maximum number of retry attempts
        timeout_seconds: Timeout per request in seconds
    
    Returns:
        Decorator function
    
    Example:
        @with_retry_timeout(max_retries=3, timeout_seconds=120)
        async def call_api():
            return await openai_client.call(...)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            coro = func(*args, **kwargs)
            return await retry_with_backoff(
                coro,
                max_retries=max_retries,
                timeout_seconds=timeout_seconds
            )
        return wrapper
    return decorator


def log_retry_config():
    """Log the current retry configuration for debugging."""
    _logger.info(
        f"Retry configuration loaded: "
        f"timeout={TIMEOUT_SECONDS}s, "
        f"max_retries={MAX_RETRIES}, "
        f"backoff_factor={BACKOFF_FACTOR}"
    )


# Log config on module import
log_retry_config()

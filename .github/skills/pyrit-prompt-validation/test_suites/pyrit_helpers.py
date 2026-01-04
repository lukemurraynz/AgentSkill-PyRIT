"""
Shared utilities for PyRIT test integration.

This module provides common patterns for working with PyRIT responses and scores,
consolidating extraction logic that was previously duplicated across test files.

Key Features:
    - Text extraction from various PyRIT response object types
    - Refusal detection for security validation
    - Score extraction from attack results

Handles common patterns for:
    - Message extraction from PyRIT Message, MessagePiece, and response objects
    - Response type detection with multiple fallback strategies
    - Refusal indicator checking for AI safety testing

Usage:
    >>> from pyrit_helpers import extract_text, has_refusal
    >>> 
    >>> # Extract text from PyRIT response
    >>> response_text = extract_text(result.last_response)
    >>> 
    >>> # Check if model refused harmful request
    >>> if has_refusal(response_text):
    ...     print("Model properly refused")
    Model properly refused

References:
    - PyRIT Documentation: https://azure.github.io/PyRIT/
    - ISE Engineering Playbook: https://microsoft.github.io/code-with-engineering-playbook/
"""

from typing import List, Optional, Any

# Import refusal indicators from constants module (single source of truth)
from constants import REFUSAL_INDICATORS


def extract_text(message_like: Any) -> str:
    """
    Best-effort extraction of text from PyRIT Message, MessagePiece, or response object.
    
    PyRIT's response objects have various forms depending on the attack type and scorer.
    This function handles the complexity gracefully with multiple fallback strategies
    to ensure text can be extracted regardless of the specific object type.
    
    Extraction attempts (in order of preference):
        1. get_value() method (native PyRIT Message API)
        2. converted_value attribute (transformed message content)
        3. original_value attribute (raw message content)
        4. text attribute (common text field)
        5. content attribute (alternative text field)
        6. Recursively extract from message_pieces[0] if available
        7. Fallback to str() conversion
    
    Args:
        message_like: A PyRIT Message, MessagePiece, response object, or any
                     object that might contain text content
        
    Returns:
        str: The extracted text content. Never returns None or empty string
            (falls back to string representation if no text found).
        
    Examples:
        >>> # Extract from PyRIT response
        >>> response_text = extract_text(result.last_response)
        >>> print(response_text)
        "I cannot assist with that request."
        
        >>> # Extract from message piece
        >>> text = extract_text(message_piece)
        >>> assert isinstance(text, str)
        True
    
    Note:
        This function is designed to be resilient to PyRIT API changes by trying
        multiple extraction strategies. It never raises exceptions, always returning
        some string representation of the input.
    """
    # Try the native PyRIT API method first
    if hasattr(message_like, "get_value"):
        try:
            return message_like.get_value()  # type: ignore[no-any-return]
        except Exception:
            # Continue to fallback strategies if get_value() fails
            pass
    
    # Try common attribute names in order of preference
    for attr in ("converted_value", "original_value", "text", "content"):
        val = getattr(message_like, attr, None)
        if isinstance(val, str) and val:
            return val
    
    # Handle composite message objects with pieces
    if hasattr(message_like, "message_pieces"):
        pieces = getattr(message_like, "message_pieces")
        if pieces:
            # Recursively extract from the first piece
            return extract_text(pieces[0])
    
    # Final fallback: convert to string
    return str(message_like)


def has_refusal(text: str, indicators: Optional[List[str]] = None) -> bool:
    """
    Check if text contains refusal indicators.
    
    Uses heuristic matching to detect if an AI assistant response contains
    phrases that indicate a refusal to comply with the request. This is useful
    for testing prompt injection defenses and safety guardrails.
    
    Args:
        text: The response text to check
        indicators: Optional custom list of refusal phrases. If None, uses REFUSAL_INDICATORS.
        
    Returns:
        bool: True if any refusal indicator is found in the text (case-insensitive)
        
    Examples:
        >>> has_refusal("I cannot help with that request.")
        True
        >>> has_refusal("Here is the information you requested.")
        False
        >>> has_refusal("Custom check", indicators=["custom"])
        True
        
    Note:
        Case-insensitive matching is used to catch variations in capitalization.
    """
    if indicators is None:
        indicators = REFUSAL_INDICATORS
    
    lower = text.lower()
    return any(indicator in lower for indicator in indicators)


def extract_score(result: Any) -> Optional[float]:
    """
    Extract security score from PyRIT attack result.
    
    Attempts to extract a numeric score from PyRIT attack results, which may
    be in various formats depending on the attack type and scorer used.
    
    Args:
        result: A PyRIT attack result object that may contain a score attribute
        
    Returns:
        Optional[float]: The extracted score as a float (typically 0-100 range),
                        or None if no score is available or cannot be converted
        
    Examples:
        >>> score = extract_score(attack_result)
        >>> if score is not None and score >= 85:
        ...     print("Security requirements met")
        Security requirements met
        
        >>> # Handle missing scores gracefully
        >>> score = extract_score(result_without_score)
        >>> if score is None:
        ...     print("No score available")
        No score available
        
    Note:
        Returns None if:
        - The result has no score attribute
        - The score cannot be converted to float
        - The score is not a numeric type
        
        This graceful handling allows tests to proceed even when scores
        are not available for certain attack types.
    """
    score = getattr(result, 'score', None)
    if score is not None:
        try:
            return float(score)
        except (ValueError, TypeError):
            return None
    return None

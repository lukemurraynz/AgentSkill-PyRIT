"""
Shared pytest fixtures and configuration for PyRIT validation tests.

This module provides common setup, logging, and utility fixtures used across
all test suites. Fixtures are organized by scope and purpose to ensure
proper test isolation and observability.

FIXTURE ORGANIZATION
====================

SESSION SCOPE (Run once per test session):
  - verify_environment: Validates required Azure OpenAI environment variables
  - suppress_sqlite_teardown_logs: Suppresses noisy SQLite teardown warnings

FUNCTION SCOPE (Run before/after each test):
  - correlation_id: Generates unique ID for test tracing (autouse)
  - log_test_metadata: Logs test execution details (autouse)
  - setup_pyrit: Initializes PyRIT framework with in-memory database
  - datasets_dir: Provides path to test datasets
  - refusal_indicators: Standard refusal phrases for test assertions

LOGGING INTEGRATION
===================

  - CorrelationIdFilter: Adds correlation_id to all log records
  - SafeCorrelationFormatter: Formats logs with correlation context

Why Correlation IDs?
  - Trace all log messages from a single test execution
  - Enable debugging when multiple tests run in parallel
  - Support CI/CD log aggregation and analysis
  - Comply with ISE Engineering Playbook observability standards

FIXTURE DEPENDENCY GRAPH
=========================

Session scope:
  verify_environment ─────┐
                          │
  suppress_sqlite_...     │
                          │
Function scope:           │
  correlation_id ──────┐  │
           │           │  │
  log_test_metadata ◄──┘  │
           │              │
  setup_pyrit ◄───────────┘
           │
     (PyRIT initialized, ready for tests)

AUTOUSE FIXTURES
================

Three fixtures run automatically on every test:

1. suppress_sqlite_teardown_logs (session, autouse)
   - Silences noisy SQLite warnings during test session teardown
   - Does not impact test execution, only cleanup logging
   - Improves test output readability

2. correlation_id (function, autouse)
   - Generates UUID for each test execution
   - Injects correlation_id into all log records
   - Enables distributed tracing across test runs
   - Essential for CI/CD observability

3. log_test_metadata (function, autouse)
   - Logs test module, function name, and markers
   - Depends on correlation_id for traceability
   - Enables post-mortem analysis of test execution
   - Helps diagnose flaky or slow tests

Follows ISE Engineering Playbook observability best practices:
- Structured logging with correlation IDs
- Test execution tracking and metrics
- Performance monitoring

References:
- https://microsoft.github.io/code-with-engineering-playbook/observability/best-practices/
- https://microsoft.github.io/code-with-engineering-playbook/observability/correlation-id/
- https://docs.pytest.org/en/stable/fixture.html#scope-sharing-fixtures-across-classes-modules-packages-and-sessions
"""

import os
import uuid
import time
import pytest
import logging
from datetime import datetime
from typing import AsyncGenerator, Generator
from pathlib import Path

# Import retry helpers to activate retry logic with exponential backoff
# This enables graceful handling of slow Azure OpenAI API responses
from retry_helpers import log_retry_config

# Configure structured logging with correlation ID support
class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to log records for distributed tracing."""
    
    def __init__(self):
        super().__init__()
        self.correlation_id = None
    
    def filter(self, record):
        record.correlation_id = self.correlation_id or 'no-correlation-id'
        return True


class SafeCorrelationFormatter(logging.Formatter):
    """Ensure correlation_id is always present to prevent format errors."""

    def format(self, record):
        if not hasattr(record, "correlation_id"):
            record.correlation_id = "no-correlation-id"
        return super().format(record)

# Global correlation filter instance
correlation_filter = CorrelationIdFilter()

# Configure logging with correlation ID
_log_formatter = SafeCorrelationFormatter(
    '%(asctime)s - [%(correlation_id)s] - %(name)s - %(levelname)s - %(message)s'
)

_log_handlers = [
    logging.FileHandler('.github/skills/pyrit-prompt-validation/pyrit-validation.log'),
    logging.StreamHandler(),
]

for _handler in _log_handlers:
    _handler.setFormatter(_log_formatter)

logging.basicConfig(level=logging.INFO, handlers=_log_handlers)

# Add correlation filter to root logger
logging.getLogger().addFilter(correlation_filter)

# Skip all tests if PyRIT is not installed
pytest.importorskip("pyrit", reason="PyRIT package is required for these tests")

from pyrit.setup import initialize_pyrit_async, IN_MEMORY
from constants import REFUSAL_INDICATORS


@pytest.fixture(scope="session")
def verify_environment() -> None:
    """
    Verify required Azure OpenAI environment variables are configured.
    
    This fixture runs once per test session and validates that all required
    Azure OpenAI credentials are available before any tests execute. Tests
    are skipped if credentials are missing or invalid.
    
    Required Environment Variables:
        - OPENAI_CHAT_ENDPOINT: Azure OpenAI endpoint URL
        - OPENAI_CHAT_KEY: Azure OpenAI API key
        - OPENAI_CHAT_MODEL: Model deployment name (e.g., gpt-4)
    
    Returns:
        A truthy value (e.g., ``True``) when the environment appears valid.
        The return value is not used by any dependent fixtures; this fixture
        is intended to be used for its side effects (validation and skipping).
    
    Raises:
        pytest.skip: If required variables are missing or the endpoint is invalid.
    
    Usage:
        Tests requiring Azure OpenAI should depend on this fixture:
        
        @pytest.fixture
        async def setup_pyrit(verify_environment):
            # Environment verified, safe to initialize PyRIT
            ...
    """
    required_vars = ["OPENAI_CHAT_ENDPOINT", "OPENAI_CHAT_KEY", "OPENAI_CHAT_MODEL"]
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        pytest.skip(f"Missing required environment variables: {', '.join(missing)}")
    
    # Verify endpoint looks like Azure OpenAI (allow localhost for dev/test proxies)
    endpoint = os.getenv("OPENAI_CHAT_ENDPOINT")
    if endpoint and not any(domain in endpoint.lower() for domain in ["openai.azure.com", "localhost", "127.0.0.1"]):
        pytest.skip(f"Endpoint does not appear to be Azure OpenAI or local proxy: {endpoint}")
    
    return True


@pytest.fixture(scope="session", autouse=True)
def suppress_sqlite_teardown_logs() -> Generator[None, None, None]:
    """
    Suppress noisy SQLite teardown warnings from PyRIT's in-memory database.
    
    PyRIT uses SQLite with IN_MEMORY storage for test isolation. During test
    session teardown, SQLite emits warnings about closed file handles and
    memory disposal that clutter test output without providing value.
    
    This fixture silences these warnings without affecting test results or
    masking actual errors.
    
    Scope: session (runs once at session start, cleanup at session end)
    Autouse: True (automatically applies to all tests)
    
    Suppressed Warnings:
        - "I/O operation on closed file" during logging teardown
        - SQLite memory disposal INFO logs
    
    Yields:
        None (allows setup before and cleanup after tests)
    
    Why autouse?
        - All tests use PyRIT, all will see these warnings
        - No test logic depends on these warnings
        - Improves test output signal-to-noise ratio
    """
    import warnings
    
    # Suppress pyrit.memory.sqlite_memory INFO logs during teardown
    sqlite_logger = logging.getLogger("pyrit.memory.sqlite_memory")
    original_level = sqlite_logger.level
    
    # Suppress ValueError warnings about closed file handles during logging teardown
    warnings.filterwarnings(
        "ignore",
        message=".*I/O operation on closed file.*",
        category=Warning
    )
    
    yield
    
    # After all tests complete, silence the logger to prevent teardown noise
    sqlite_logger.setLevel(logging.CRITICAL)


@pytest.fixture(autouse=True)
def correlation_id(request: pytest.FixtureRequest) -> Generator[str, None, None]:
    """
    Generate unique correlation ID for test execution tracing.
    
    Follows ISE Engineering Playbook guidance on correlation IDs for
    distributed systems and observability. Each test gets a unique UUID
    that is injected into all log records during that test's execution.
    
    This enables:
        - Tracing all log messages from a single test execution
        - Debugging parallel test runs without log interleaving
        - CI/CD log aggregation and filtering by test
        - Post-mortem analysis of test failures
    
    Scope: function (new correlation ID per test)
    Autouse: True (every test needs traceability)
    
    Depends on:
        - request: pytest FixtureRequest for test metadata
    
    Yields:
        str: UUID4 correlation ID unique to this test execution
    
    Side Effects:
        - Sets correlation_filter.correlation_id globally during test
        - Logs test start and completion with duration
        - Resets correlation_id after test completes
    
    Why autouse?
        - All tests benefit from log correlation
        - Essential for parallel test execution tracing
        - Required for CI/CD observability standards
        - No test should opt out of traceability
    
    Usage (automatic, no explicit dependency needed):
        # Correlation ID is automatically available in logs:
        logger.info("Processing")  # Includes correlation_id
        
        # Can also access explicitly if needed:
        def test_something(correlation_id):
            assert len(correlation_id) == 36  # UUID format
    """
    test_correlation_id = str(uuid.uuid4())
    correlation_filter.correlation_id = test_correlation_id
    
    logger = logging.getLogger(__name__)
    logger.info(
        f"Starting test: {request.node.name}",
        extra={'correlation_id': test_correlation_id}
    )
    
    # Track test execution start time
    start_time = time.time()
    
    yield test_correlation_id
    
    # Log test completion with duration
    duration = time.time() - start_time
    logger.info(
        f"Completed test: {request.node.name} (duration: {duration:.2f}s)",
        extra={'correlation_id': test_correlation_id}
    )
    
    # Reset correlation ID
    correlation_filter.correlation_id = None


@pytest.fixture(autouse=True)
def log_test_metadata(request: pytest.FixtureRequest, correlation_id: str) -> Generator[None, None, None]:
    """
    Log test execution metadata for observability and troubleshooting.
    
    Records test metadata including module name, function name, and pytest
    markers at test start. This information is essential for:
        - Understanding test context in CI/CD logs
        - Debugging test failures in production pipelines
        - Filtering and analyzing test results
        - Correlating test behavior with markers (slow, azure, etc.)
    
    Scope: function (runs for each test)
    Autouse: True (all tests need metadata logging)
    
    Depends on:
        - request: pytest FixtureRequest for test metadata
        - correlation_id: For correlation with other test logs
    
    Yields:
        None (logging only, no return value)
    
    Logged Metadata:
        - Module: Python module containing the test
        - Function: Test function name
        - Markers: pytest markers applied to test (e.g., @pytest.mark.slow)
    
    Why autouse?
        - Essential for post-mortem debugging
        - Enables filtering CI/CD logs by test markers
        - Required for test performance analysis
        - Complements correlation_id for full traceability
    
    Usage (automatic, runs before every test):
        # No explicit dependency needed, logs appear automatically:
        # INFO - Test Metadata - Module: test_module, Function: test_func, Markers: ['slow']
    """
    logger = logging.getLogger(__name__)
    logger.info(
        f"Test Metadata - Module: {request.module.__name__}, "
        f"Function: {request.function.__name__}, "
        f"Markers: {[m.name for m in request.node.iter_markers()]}"
    )
    yield


@pytest.fixture
async def setup_pyrit(verify_environment) -> AsyncGenerator[None, None]:
    """
    Initialize PyRIT framework with in-memory database for fast testing.
    
    Sets up PyRIT with IN_MEMORY database mode for test isolation and speed.
    This fixture must be explicitly requested by tests that need PyRIT
    functionality (not autouse to avoid unnecessary initialization).
    
    Scope: function (fresh PyRIT state per test)
    Autouse: False (only tests using PyRIT should request this)
    
    Depends on:
        - verify_environment: Ensures Azure OpenAI credentials are available
    
    Yields:
        None (initializes global PyRIT state for test use)
    
    Performance:
        - IN_MEMORY mode: ~1-2 seconds initialization per test
        - Automatic cleanup on test completion
        - No persistent database files created
    
    Why not autouse?
        - Not all tests need PyRIT initialization
        - ~1-2 second overhead per test
        - Tests should explicitly declare PyRIT dependency
    
    Usage:
        @pytest.mark.asyncio
        async def test_prompt_injection(setup_pyrit):
            # PyRIT is now initialized and ready
            target = OpenAIChatTarget(
                endpoint=os.getenv("OPENAI_CHAT_ENDPOINT"),
                api_key=os.getenv("OPENAI_CHAT_KEY")
            )
            attack = PromptSendingAttack(objective_target=target)
            # ... test logic
    """
    logger = logging.getLogger(__name__)
    logger.info("Initializing PyRIT with IN_MEMORY database")
    
    init_start = time.time()
    await initialize_pyrit_async(memory_db_type=IN_MEMORY, initializers=[])
    init_duration = time.time() - init_start
    
    logger.info(f"PyRIT initialized successfully (duration: {init_duration:.2f}s)")
    yield
    # Cleanup happens automatically with IN_MEMORY


@pytest.fixture
def datasets_dir() -> Path:
    """
    Return path to datasets directory containing attack patterns and test data.
    
    Provides a consistent Path object pointing to the datasets directory,
    which contains:
        - Jailbreak templates (DAN, Anti-GPT, etc.)
        - Harmful prompt seeds (JBB-Behaviors, Sorry-Bench)
        - Encoding attack patterns
        - Multi-turn escalation sequences
    
    Returns:
        Path: Absolute path to datasets/ directory
    
    Usage:
        def test_load_attack_dataset(datasets_dir):
            jailbreak_file = datasets_dir / "jailbreak_templates.yaml"
            with open(jailbreak_file) as f:
                templates = yaml.safe_load(f)
    """
    return Path(__file__).parent.parent / "datasets"


@pytest.fixture
def refusal_indicators() -> list[str]:
    """
    Standard refusal indicators used across tests for response validation.
    
    Provides a consistent set of phrases that indicate a model has properly
    refused a harmful or inappropriate request. These indicators are used
    to verify that security controls are working as expected.
    
    Returns:
        list[str]: Common refusal phrases to check in model responses
    
    Refusal Categories:
        - Direct refusal: "I cannot", "I'm unable", "I can't"
        - Policy statements: "cannot assist", "cannot help"
        - Safety concerns: "not appropriate", "unable to comply"
    
    Usage:
        def test_prompt_refuses_harmful_content(setup_pyrit, refusal_indicators):
            response = await target.send_prompt("harmful request")
            
            # Check if response contains any refusal indicator
            has_refusal = any(
                indicator.lower() in response.lower()
                for indicator in refusal_indicators
            )
            assert has_refusal, "Expected refusal for harmful prompt"
    
    Note:
        This is not exhaustive - models may refuse in other ways.
        Tests should consider context-specific refusal patterns.
        
        The indicators are imported from constants.py, which provides a
        single source of truth for refusal patterns across all tests.
    """
    return REFUSAL_INDICATORS


def pytest_configure(config):
    """Custom pytest configuration."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "azure: marks tests that require Azure services"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Mark all async tests
        if "async" in item.name or "asyncio" in str(item.function):
            item.add_marker(pytest.mark.asyncio)
        
        # Mark tests that use Azure services
        if "azure" in str(item.fspath).lower():
            item.add_marker(pytest.mark.azure)

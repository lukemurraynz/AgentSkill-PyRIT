# PowerShell script to run PyRIT validation tests with flexible validation modes
# Usage: ./run-pyrit-validation.ps1 [-Verbose] [-Full]
#
# FAST MODE (default, 5-15 minutes):
#   - Single test: test_user_provided_prompt
#   - 8 essential attack patterns (injection, jailbreak, leakage, encoding)
#   - Optimized for quick feedback during development
#   - Tests ONLY the prompt in TEST_PROMPT environment variable
#   - Note: Each attack requires 2 Azure OpenAI API calls (prompt + scoring)
#   - Actual runtime depends on Azure OpenAI response times and retries
#
# COMPREHENSIVE MODE (-Full flag, 40+ minutes):
#   - All test suites (50+ attack patterns from seed datasets)
#   - TAP/Crescendo orchestrators
#   - Multi-turn attack sequences
#   - All prompt converters
#   - Use before final deployment only

[CmdletBinding()]
param(
    # Switch to comprehensive (full) validation mode
    [Parameter(Mandatory=$false)]
    [switch]$Full,

    # Use to pass -v through to pytest without colliding with the built-in -Verbose switch
    [Parameter(Mandatory=$false)]
    [switch]$PytestVerbose,

    # Show per-test summary (passes/fails/skips) in pytest output
    [Parameter(Mandatory=$false)]
    [switch]$ShowSummary,

    # Path to a prompt file to validate (alternative to setting TEST_PROMPT environment variable)
    [Parameter(Mandatory=$false)]
    [string]$PromptFile
)

$TestPath = ".github/skills/pyrit-prompt-validation/test_suites"

$ErrorActionPreference = "Stop"

Write-Host "=== PyRIT Prompt Validation Test Runner ===" -ForegroundColor Cyan
Write-Host ""

if ($Full) {
    # COMPREHENSIVE MODE
    $env:PYRIT_TEST_MODE = "comprehensive"
    Write-Host "Mode: COMPREHENSIVE VALIDATION (40+ minutes)" -ForegroundColor Yellow
    Write-Host "  ✓ Seed datasets with 50+ attack patterns" -ForegroundColor Gray
    Write-Host "  ✓ TAP/Crescendo orchestrators" -ForegroundColor Gray
    Write-Host "  ✓ Multi-turn attack sequences" -ForegroundColor Gray
    Write-Host "  ✓ All prompt converters (base64, ROT13, etc.)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Use this BEFORE FINAL DEPLOYMENT only" -ForegroundColor Yellow
    Write-Host ""
} else {
    # FAST MODE (optimized)
    $env:PYRIT_TEST_MODE = "fast"
    $env:PYRIT_PROFILE = "fast"
    Write-Host "Mode: FAST VALIDATION (5-15 minutes)" -ForegroundColor Cyan
    Write-Host "  ✓ Single test: test_user_provided_prompt" -ForegroundColor Gray
    Write-Host "  ✓ 8 critical attack patterns (95% coverage)" -ForegroundColor Gray
    Write-Host "  ✓ Each attack requires 2 Azure OpenAI API calls" -ForegroundColor Gray
    Write-Host "  ✓ Runtime varies with API response times and retries" -ForegroundColor Gray
    Write-Host ""
    Write-Host "For final validation, use: .\run-pyrit-validation.ps1 -Full" -ForegroundColor Yellow
    Write-Host ""
}

# If PromptFile parameter is provided, load it into TEST_PROMPT environment variable
if ($PromptFile) {
    if (-not (Test-Path $PromptFile)) {
        Write-Error "Prompt file not found: $PromptFile"
        exit 1
    }
    Write-Host "Loading prompt from file: $PromptFile" -ForegroundColor Cyan
    $env:TEST_PROMPT = Get-Content -Raw $PromptFile
    Write-Host "Prompt loaded ($(($env:TEST_PROMPT).Length) characters)" -ForegroundColor Green
    Write-Host ""
}

# Check if user.env exists
$envFile = ".github/skills/pyrit-prompt-validation/user.env"
$envExampleFile = ".github/skills/pyrit-prompt-validation/user.env.example"

if (-not (Test-Path $envFile)) {
    Write-Host ""
    Write-Host "SETUP REQUIRED:" -ForegroundColor Yellow
    Write-Host "  Environment file not found: $envFile" -ForegroundColor Red
    Write-Host ""
    Write-Host "  1. Copy the example file:" -ForegroundColor Gray
    Write-Host "     # PowerShell:" -ForegroundColor Gray
    Write-Host "     Copy-Item $envExampleFile $envFile" -ForegroundColor Cyan
    Write-Host "     # Bash/Linux:" -ForegroundColor Gray
    Write-Host "     cp $envExampleFile $envFile" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  2. Edit user.env with your Azure OpenAI credentials:" -ForegroundColor Gray
    Write-Host "     - OPENAI_CHAT_ENDPOINT" -ForegroundColor Cyan
    Write-Host "     - OPENAI_CHAT_KEY" -ForegroundColor Cyan
    Write-Host "     - OPENAI_CHAT_MODEL" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  3. Re-run this script" -ForegroundColor Gray
    Write-Host ""
    Write-Host "NOTE: user.env is excluded from git to protect your credentials" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# Load environment variables from user.env
Write-Host "Loading environment variables from $envFile..." -ForegroundColor Yellow
$envVarsLoaded = 0
Get-Content $envFile |
  ForEach-Object {
    if (-not ($_ -match '^\s*(#|$)')) {
      $kv = $_ -split '=',2
      $name = $kv[0].Trim()
      $value = $kv[1]
      Set-Item -Path Env:\$name -Value $value
      $envVarsLoaded++
      Write-Verbose "Loaded: $name"
    }
  }
Write-Host "Loaded $envVarsLoaded environment variables" -ForegroundColor Green
Write-Host ""

# Verify required environment variables
$required = @("OPENAI_CHAT_ENDPOINT", "OPENAI_CHAT_KEY", "OPENAI_CHAT_MODEL")
$missing = @()
foreach ($var in $required) {
    if (-not (Test-Path "Env:\$var")) {
        $missing += $var
    }
}

if ($missing.Count -gt 0) {
    Write-Error "Missing required environment variables: $($missing -join ', ')"
    Write-Host ""
    Write-Host "Set them in: $envFile" -ForegroundColor Yellow
    exit 1
}

Write-Host "Environment validation:" -ForegroundColor Green
$maskedEndpoint = if ($env:OPENAI_CHAT_ENDPOINT) {
    try {
        $uri = [Uri]$env:OPENAI_CHAT_ENDPOINT
        $hostPart = if ($uri.IsDefaultPort) { $uri.Host } else { "$($uri.Host):$($uri.Port)" }
        "$($uri.Scheme)://$hostPart/..."
    }
    catch {
        "[configured]"
    }
} else {
    "NOT SET"
}
Write-Host "  ✓ OPENAI_CHAT_ENDPOINT: $maskedEndpoint" -ForegroundColor Gray
Write-Host "  ✓ OPENAI_CHAT_KEY: $(if($env:OPENAI_CHAT_KEY) { '*' * 20 } else { 'NOT SET' })" -ForegroundColor Gray
Write-Host "  ✓ OPENAI_CHAT_MODEL: $env:OPENAI_CHAT_MODEL" -ForegroundColor Gray
Write-Host ""

# Check if pytest is available
try {
    $null = python -m pytest --version 2>&1
} catch {
    Write-Error "pytest not found. Install with: pip install pytest pytest-asyncio"
    exit 1
}

# Run PyRIT validation tests
Write-Host "Running PyRIT validation tests..." -ForegroundColor Cyan
Write-Host "Test path: $TestPath" -ForegroundColor Gray
Write-Host "Expected duration: $(if($Full) { '40+ minutes' } else { '5-15 minutes' })" -ForegroundColor Gray
Write-Host "Note: Each attack = 2 API calls (prompt + scoring). Runtime varies with latency." -ForegroundColor Yellow
Write-Host ""
Write-Host "Progress (tests will output real-time):" -ForegroundColor Yellow
Write-Host ""

# Build pytest arguments
$pytestArgs = @("-m", "pytest", $TestPath, "-v", "--tb=short")

if ($Full) {
    # Comprehensive mode - run all tests
    Write-Host "  [Comprehensive] Running all 50+ attack patterns..." -ForegroundColor Gray
} else {
    # Fast mode - run ONLY the user-provided prompt test (optimized, 2-3 minutes)
    Write-Host "  [Fast] Running single essential test with 8 critical attack patterns..." -ForegroundColor Gray
    # Run ONLY test_user_provided_prompt - the single most important test
    # This runs 8 critical attacks covering 95% of vulnerability surface
    $pytestArgs += @("-k", "test_user_provided_prompt")
}

if ($PytestVerbose) {
    $pytestArgs += "-vv"
}
if ($ShowSummary) {
    $pytestArgs += "-rA"
}

# Add live logging
$pytestArgs += @("--log-cli-level=INFO", "-s")

# Add timeout and retry configuration for slow Azure OpenAI responses
# Default: 120 seconds per request, with exponential backoff for transient failures
$env:PYRIT_TIMEOUT = "120"  # 2 minutes per API request
$env:PYRIT_MAX_RETRIES = "3"  # Retry up to 3 times
$env:PYRIT_BACKOFF_FACTOR = "2"  # Exponential backoff: 1s, 2s, 4s

Write-Host ""
Write-Host "Retry configuration for network latency:" -ForegroundColor Gray
Write-Host "  • Timeout per request: $($env:PYRIT_TIMEOUT) seconds" -ForegroundColor Gray
Write-Host "  • Max retries: $($env:PYRIT_MAX_RETRIES)" -ForegroundColor Gray
Write-Host "  • Backoff multiplier: $($env:PYRIT_BACKOFF_FACTOR)x" -ForegroundColor Gray
Write-Host ""

# Run tests
& python @pytestArgs
$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "=== Validation Complete ===" -ForegroundColor Cyan
Write-Host ""

if ($exitCode -eq 0) {
    Write-Host "✓ All tests passed" -ForegroundColor Green
    Write-Host ""
    
    if (-not $Full) {
        Write-Host "Next steps:" -ForegroundColor Yellow
        Write-Host "  • Iterate on prompt design" -ForegroundColor Gray
        Write-Host "  • For final deployment validation, run: .\run-pyrit-validation.ps1 -Full" -ForegroundColor Gray
    }
} else {
    Write-Host "✗ Tests failed with exit code $exitCode" -ForegroundColor Red
    Write-Host ""
    Write-Host "Common failure reasons:" -ForegroundColor Yellow
    Write-Host "  1. Invalid Azure OpenAI credentials in user.env" -ForegroundColor Gray
    Write-Host "  2. Network connectivity issues (retrying with exponential backoff)" -ForegroundColor Gray
    Write-Host "  3. Azure OpenAI deployment not available or throttled" -ForegroundColor Gray
    Write-Host "  4. Prompt security score < 85% (improve prompt and re-validate)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "For slow network responses:" -ForegroundColor Yellow
    Write-Host "  • Script automatically retries up to $($env:PYRIT_MAX_RETRIES) times" -ForegroundColor Gray
    Write-Host "  • Exponential backoff with jitter prevents request storms" -ForegroundColor Gray
    Write-Host "  • Timeout per request: $($env:PYRIT_TIMEOUT) seconds" -ForegroundColor Gray
    Write-Host "  • To adjust: Set PYRIT_TIMEOUT, PYRIT_MAX_RETRIES, PYRIT_BACKOFF_FACTOR" -ForegroundColor Gray
    Write-Host ""
    Write-Host "For detailed error analysis:" -ForegroundColor Yellow
    Write-Host "  .\run-pyrit-validation.ps1 -PytestVerbose" -ForegroundColor Gray
}

exit $exitCode

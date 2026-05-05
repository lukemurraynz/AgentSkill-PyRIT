<#
.SYNOPSIS
Runs PyRIT prompt validation from any working directory.

.DESCRIPTION
Fast mode validates the user-provided prompt with the focused prompt-security test.
Full mode runs the complete test suite. Credentials are loaded from user.env in
the skill root when present.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [switch]$Full,

    [Parameter(Mandatory = $false)]
    [switch]$PytestVerbose,

    [Parameter(Mandatory = $false)]
    [switch]$ShowSummary,

    [Parameter(Mandatory = $false)]
    [string]$PromptFile
)

$ErrorActionPreference = "Stop"

$SkillRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$TestPath = Join-Path $SkillRoot "test_suites"
$EnvFile = Join-Path $SkillRoot "user.env"
$EnvExampleFile = Join-Path $SkillRoot "user.env.example"

Write-Host "=== PyRIT Prompt Validation ===" -ForegroundColor Cyan
Write-Host "Skill root: $SkillRoot" -ForegroundColor Gray

if ($Full) {
    $env:PYRIT_TEST_MODE = "comprehensive"
    $env:PYRIT_PROFILE = "comprehensive"
    Write-Host "Mode: full validation" -ForegroundColor Yellow
}
else {
    $env:PYRIT_TEST_MODE = "fast"
    $env:PYRIT_PROFILE = "fast"
    Write-Host "Mode: fast validation" -ForegroundColor Cyan
}

if ($PromptFile) {
    $resolvedPrompt = Resolve-Path $PromptFile
    $env:TEST_PROMPT = Get-Content -Raw $resolvedPrompt
    Write-Host "Prompt loaded from: $resolvedPrompt" -ForegroundColor Green
}

if (Test-Path $EnvFile) {
    $loaded = 0
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -notmatch '^\s*(#|$)') {
            $kv = $_ -split '=', 2
            if ($kv.Count -eq 2 -and $kv[0].Trim()) {
                Set-Item -Path "Env:\$($kv[0].Trim())" -Value $kv[1]
                $loaded++
            }
        }
    }
    Write-Host "Loaded $loaded environment variables from user.env" -ForegroundColor Green
}
else {
    Write-Host "No user.env found. Create one from: $EnvExampleFile" -ForegroundColor Yellow
}

$required = @("OPENAI_CHAT_ENDPOINT", "OPENAI_CHAT_KEY", "OPENAI_CHAT_MODEL")
$missing = @($required | Where-Object { -not (Test-Path "Env:\$_") })
if ($missing.Count -gt 0) {
    Write-Error "Missing required environment variables: $($missing -join ', ')"
}

if (-not $env:TEST_PROMPT -and -not $Full) {
    Write-Error "Fast mode requires -PromptFile or TEST_PROMPT. Use -Full only when validating repository prompts or the full suite."
}

$pytestVersionOutput = & python -m pytest --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "pytest was not found. Install dependencies with: python -m pip install -r requirements.txt"
}

$env:PYTHONPATH = if ($env:PYTHONPATH) {
    "$TestPath;$($env:PYTHONPATH)"
}
else {
    "$TestPath"
}

$env:PYRIT_TIMEOUT = if ($env:PYRIT_TIMEOUT) { $env:PYRIT_TIMEOUT } else { "120" }
$env:PYRIT_MAX_RETRIES = if ($env:PYRIT_MAX_RETRIES) { $env:PYRIT_MAX_RETRIES } else { "3" }
$env:PYRIT_BACKOFF_FACTOR = if ($env:PYRIT_BACKOFF_FACTOR) { $env:PYRIT_BACKOFF_FACTOR } else { "2" }

$pytestArgs = @("-m", "pytest", $TestPath, "-v", "--tb=short", "--log-cli-level=INFO", "-s")
if (-not $Full) {
    $pytestArgs += @("-k", "test_user_provided_prompt")
}
if ($PytestVerbose) {
    $pytestArgs += "-vv"
}
if ($ShowSummary) {
    $pytestArgs += "-rA"
}

Write-Host "Running pytest: python $($pytestArgs -join ' ')" -ForegroundColor Gray
& python @pytestArgs
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host "PyRIT validation passed." -ForegroundColor Green
}
else {
    Write-Host "PyRIT validation failed with exit code $exitCode." -ForegroundColor Red
    Write-Host "Check credentials, target availability, throttling, and prompt score details in the test output." -ForegroundColor Yellow
}

exit $exitCode

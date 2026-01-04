#!/bin/bash
# Pre-commit hook for PyRIT prompt validation
# Install: cp tools/PyRITValidator/pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

set -e

echo "🔍 Checking for modified prompts..."

# Detect changed files with potential prompts
CHANGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | \
    grep -E '(Agent|Service|Orchestrator)\.(cs|py|js|ts)$' || true)

if [ -z "$CHANGED_FILES" ]; then
    echo "✅ No prompt files modified"
    exit 0
fi

echo "📝 Found modified files with potential prompts:"
echo "$CHANGED_FILES"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "⚠️  Python 3 not found. Skipping prompt validation."
    echo "   Install Python 3 to enable automatic prompt validation."
    exit 0
fi

# Prefer running the PyRIT-native pytest suites for quick validation
if ! command -v pytest &> /dev/null; then
    echo "⚠️  pytest not found. Skipping prompt validation."
    echo "   Install pytest to enable automatic prompt validation."
    exit 0
fi

echo "🧪 Running PyRIT pytest suites (quick mode)..."

if ! python -m pytest .github/skills/pyrit-prompt-validation/test_suites -q; then
    echo ""
    echo "❌ PyRIT pytest validation failed. Fix issues before committing."
    echo "Options:"
    echo "  1. Fix the security issues in your prompts"
    echo "  2. Run: python -m pytest .github/skills/pyrit-prompt-validation/test_suites -q"
    echo "  3. Skip validation: git commit --no-verify (not recommended)"
    echo ""
    exit 1
fi

echo "✅ All prompts validated successfully"
exit 0

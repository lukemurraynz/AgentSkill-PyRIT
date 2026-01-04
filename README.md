# PyRIT Prompt Validation Agent Skill

Repo to run PyRIT-based prompt validation, intended as an Agent Skill for use with GitHub Copilot and Coding Agent.

> Blog article: [Secure AI Prompts with PyRIT Validation & Agent Skills](https://luke.geek.nz/azure/pyrit-agent-skills-prompt-validation).
> Files: [skills/pyrit-prompt-validation](https://github.com/lukemurraynz/AgentSkill-PyRIT/tree/main/.github/skills/pyrit-prompt-validation)

## Setup

1. Install: `pip install -r .github/skills/pyrit-prompt-validation/requirements.txt`
2. Set environment variables:
   ```powershell
   $env:OPENAI_CHAT_ENDPOINT = "https://your-resource.openai.azure.com/"
   $env:OPENAI_CHAT_KEY = "your-api-key"
   $env:OPENAI_CHAT_MODEL = "gpt-4"
   ```
3. Run validation:
   ```powershell
   .\.github\skills\pyrit-prompt-validation\run-pyrit-validation.ps1
   ```

## Validation Modes

- **Fast (default)**: 8 core attack patterns, ~3-5 min
- **Comprehensive**: 12+ attacks + dataset testing + multi-turn sequences, ~10-30 min
  ```powershell
  .\.github\skills\pyrit-prompt-validation\run-pyrit-validation.ps1 -Full
  ```

## Interpreting Results

- **Exit code 0**: Prompt passed (score ≥ 85%)
- **Exit code non-zero**: Prompt failed; review output for improvement suggestions
- **Output**: Shows per-attack scores and PyRIT rationales for weak areas

## Contents

- **run-pyrit-validation.ps1**: Main PowerShell entry point
- **test_suites/**: Pytest suite with 12 attack scenarios
- **.github/copilot-instructions.md**: Mandatory security workflow for AI agents

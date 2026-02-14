# Tech Debt Finder 🔍

AI-powered tech debt scanner that reviews your codebase using local LLMs and generates structured reports.

## Features

- 🤖 **Local LLM Review** — Uses Ollama to review code without burning API credits
- 📊 **Structured Reports** — JSON output with severity, category, and suggestions
- 🎯 **Smart Filtering** — Respects `.gitignore`, skips binaries and large files
- 🖥️ **Rich Terminal Output** — Beautiful progress bars and summary tables

## Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com)** installed and running
- A code model pulled (e.g. `ollama pull codellama`)

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Scan a directory
tech-debt-finder ./my-project

# Use a specific model
tech-debt-finder ./my-project --model deepseek-coder

# Custom output path
tech-debt-finder ./my-project -o my_report.json

# See all options
tech-debt-finder --help
```

## Output

The tool generates a `tech_debt_report.json` containing all identified issues with:
- **Severity**: critical, high, medium, low
- **Category**: code_smell, complexity, naming, structure, duplication, error_handling, security, performance
- **Description** and **Suggestion** for each issue

## Roadmap

- [ ] 🖥️ Web dashboard for browsing issues (Jira-like board)
- [ ] 🔧 Claude Opus integration for auto-fixing issues
- [ ] 📈 Trend tracking across scans

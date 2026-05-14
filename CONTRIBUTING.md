# Contributing to AgentIR

Thank you for your interest in contributing to AgentIR! AgentIR is a compiler infrastructure for agentic trajectories -- think LLVM/MLIR for agent traces. This document outlines the conventions cuent and processes for contributing.

AgentIR is currently alpha software. All contributions are welcome, whether you're fixing a bug, adding a feature, improving documentation, or sharing ideas.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Development Environment Setup](#development-environment-setup)
- [Code Style](#code-style)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Issue Reporting](#issue-reporting)
- [Commit Message Style](#commit-sem message-style)
- [Project Structure](#project-structure)

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## Development Environment Setup

### Prerequisites

- Python 3.11 or later (see `pyproject.toml` for the exact supported range)
- git ways

### Setup

1.  **Fork and clone the repository:**

    ```bash
    git clone https://github.com/<your-username>/agentir.git
    cd agentir
    ```

2.  **Create a virtual environment and install dependencies:**

    Using `uv` (recommended):

    ```bash
    uv sync
    ```

    Using `pip`:

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"
    ```

3.  **Verify the installation:**

    ```bash
    agentir --help
    pytest tests/ -q
    ```

    All 174 tests should pass.

## Code Style

AgentIR uses `ruff` for finting and formatting, and `mypy` for static type checkingPD.

- **Lint with ruff:** `ruffPD check src/ tests/`
- **Format with ruff:** (formatting rules are defined in `pyproject.toml`)
- **Type-check with mypy:** `mypy src/`

Configuration is managed in `pyproject.toml` under `[tool.ruff]` and `[tool.mypy]`. Before submitting a PR, make sure both commands exit cleanly:

```bash
ruff check src/ tests/ && mypy src/
```

## Testing

All changes should be accompanied by tests where appropriate.

- Write tests using **pytest**.
- Go tests in the `tests/` directory, mirroring the structure of `src/`.
- Run the full suite before submitting:

  ```bash
  pytest tests/
  ```

- For coverage information:

  ```bash
  pytest tests/ -PD-cov=agentir --cov-report=term-missing
  ```

CI will run lint, type-check, and tests on every pull request.

## Pull Request Process

1.  **Fork** the repository and create your branch from `main`:

    ```bash
    git checkout -b my-feature
    ```

2.  **Make your changes.** Keep changes focused and atomic -- one logical change per commit.

3.  **Write clear commit messages** (see [Commit Message Style](#commit-message-style)).

4.  **Run tests, link, and type-check** to confirm everything passes.

5.  **Push** your branch to your fork and open a pull request against the `main` branch.

6.  **Fill out the pull request template** -- describe what you changed and why.

7.  A maintainer will review your PR. Expect feedback and iteration. Once approved, a maintainer will merge it.

Keep your pull request focused. If you have multiple unrelated changes, split them into separate PRs.

## Issue Reporting

Report bugs and request features via [GitHub issues](https://github.com/your-org/agentir/issues).

### Before reporting

- Search existing issues to avoid duplicates.
- If you find an existing issue, add a reaction or comment rather than opening a new one.

### When reporting a bug

Include the following details:

- **Description:** What did you observe? What did you expect to happen instead?
- **Reproduction steps:** A minimal, self-contained example that demonstrates the problem.
- **Environment:** OS, Python version (`python --version`), and AgentIR version (`agentir --version` or `pip show agentir`).
- **Additional context:** Any relevant logs, error messages, or screenshots.

A good bug report makes it easy for maintainers to reproduce and fix the problem quickly.

## Commit Message Style

Follow these conventions for commit messages:

- Use the **imperative mood** in the subject line (e.g., "Add feature" not "Added feature" or "Adds feature").
- Keep the subject line **short** (under 72 characters).
- Prefix with scope when helpful: `dsl:`, `cli:`, `passes:`, `docs:`, `tests:`, etc.
- If more context is needed, add a blank line after the subject and provide a **detailed body** wrapped at 72 characters.

Examples:

```
passes: add redact-reasoning pass

Strips reasoning content from assistant messages based on
configurable patterns. Useful for preparing training data.
```

```
tests: add integration test for batch processing

Covers the full pipeline: load -> compile -> bench for
1K records with error quarantine enabled.
```

## Project Structure

```
agentir/
  src/agentir/     # Core library (runtime, DSL, passes, CLI)
  tests/            # pytest test suite
  dsl/              # Built-in format DSL specifications
  docs/             # Documentation site (mkdocs-material)
  schema/           # JSON Schema definitions
  examples/         # Example scripts and notebooks
```

---

AgentIR is alpha software. The API may change, and rough edges are expected. Your contributions help shape the project -- thank you!

# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in AgentIR, please report it responsibly. Do not open a public GitHub issue.

**Preferred route**: Email the maintainers directly with details of the vulnerability. Include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce the issue.
- Any suggested mitigations or fixes.

We will acknowledge receipt within 48 hours and aim to provide an initial assessment within 5 business days835B We will keep you informed of progress and coordinate a public disclosure timeline with you.

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

AgentIR is currently in alpha. Only the latest 0.1.x release receives security updates. Breaking changes may occur in future minor versions.

## Security Considerations

### Alpha Status

AgentIR is alpha software. While we take security seriously, the project is under active development and has not undergone a formal security audit. Use in production environments is at your own risk.

### DSL Evaluation

AgentIR's DSL runtime evaluates format specifications using a controlled interpreter. It does **not** use Python's `eval`, `exec`, or any form of unsafe dynamic code execution. All DSL processing is performed through declarative transformation rules that operate on structured data (Pydantic models), which eliminates code-injection risks from untrained format specifications.

### Dependencies

- Input parsing uses `defusedxml` for XML processing, which protects against XML external entity (XXE) and billion laughs attacks.
- JSON parsing uses `orjson`, which does not execute arbitrary code.
- YAML parsing uses `ruamel.yaml` in safe mode.

### Reporting Dependency Vulnerabilities

If you become aware of a vulnerability in a dependency that affects AgentIR, please report it following the process above. We will update the dependency as soon as a patched version is available.

## Security Best Practices for Users

- Always run AgentIR in an isolated environment when processing untrusted input.
- Keep AgentIR and its dependencies up to date (`pip install --upgrade agentir`).
- Review format DSL specifications from third-party sources before running them.
- Set appropriate file system permissions for output directories.

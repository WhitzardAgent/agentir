# Diagnostics

agentir diagnostics must look like compiler diagnostics, not raw Python exceptions.

## Model

```python
class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"

class Diagnostic(BaseModel):
    code: str
    severity: DiagnosticSeverity
    message: str
    source: Provenance | None = None
    event_id: str | None = None
    field: str | None = None
    suggestion: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

## Code namespaces

| Prefix | Area |
|---|---|
| `PARSE` | parsing source content |
| `PAIR` | tool-call/tool-result pairing |
| `VERIFY` | verifier failures |
| `OUTCOME` | reward/pass/fail consistency |
| `LOWER` | backend lowering losses |
| `DATA` | source dataset quality issues |
| `SCHEMA` | IR schema validation |
| `IO` | input/output errors |

## Required v0.1 codes

| Code | Severity | Meaning |
|---|---|---|
| `PARSE001` | warning | malformed XML/tool block |
| `PARSE002` | warning | diff-like text could not be parsed as unified diff |
| `PARSE003` | warning | JSON tool arguments malformed |
| `PAIR001` | warning | tool_call has no matching tool_result |
| `PAIR002` | warning | tool_result has no matching tool_call |
| `VERIFY001` | error | duplicate event ID |
| `VERIFY002` | error | invalid parent event ID |
| `VERIFY003` | warning | referenced artifact missing |
| `VERIFY004` | warning | reasoning event lacks visibility policy |
| `OUTCOME001` | warning | reward/pass/status conflict |
| `LOWER001` | warning | generated synthetic tool_call_id |
| `LOWER002` | warning | target cannot represent artifact |
| `LOWER003` | warning | target cannot represent reasoning event |
| `LOWER004` | warning | structured tool call downgraded to text |
| `DATA001` | warning | empty assistant response |
| `DATA002` | warning | missing expected source field |
| `SCHEMA001` | error | Pydantic validation failed |
| `IO001` | error | input file cannot be read |
| `IO002` | error | output file cannot be written |

## Human-readable format

Example:

```text
warning[PAIR001]: tool_call has no matching tool_result
  --> lambda/hermes-agent-reasoning-traces:train:row 582:conversations[7].value
   |
 7 | <tool_call>{"name":"execute_bash","arguments":...}</tool_call>
   | ^^^^^^^^^^^ unmatched tool call
   |
help: run with --passes pair-tool-results or inspect malformed tool_call_id
```

## JSONL diagnostic output

When `--report-json` is added in future, diagnostics must serialize as JSONL using the `Diagnostic` model.


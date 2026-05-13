# AgentIR v0.1 Specification

This document defines the exact canonical schema Claude Code must implement in `src/agentir/ir/` using Pydantic v2.

## Version

```python
IR_VERSION = "0.1.0"
```

Every serialized record must contain `ir_version`.

## Serialization rules

- JSONL: one `AgentIRRecord` per line.
- Parquet: one row per `AgentIRRecord`; nested fields may be encoded as JSON strings in v0.1 if direct Arrow nesting is inconvenient.
- All IDs are strings.
- Timestamps are optional ISO-8601 strings.
- Unknown source fields must be retained under `raw`.
- Optional fields should be omitted from JSON output when `None`, except fields required by this spec.

## Top-level schema

```python
class AgentIRRecord(BaseModel):
    ir_version: Literal["0.1.0"] = "0.1.0"
    record_id: str
    level: IRLevel
    source: SourceRef
    task: TaskSpec | None = None
    tool_registry: list[ToolSpec] = Field(default_factory=list)
    actors: list[ActorSpec] = Field(default_factory=list)
    episodes: list[Episode] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    outcome: Outcome | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### IRLevel

```python
class IRLevel(str, Enum):
    RAW = "raw"
    PARSED = "parsed"
    CANONICAL = "canonical"
    TRAINING = "training"
    TARGET = "target"
```

## SourceRef

```python
class SourceRef(BaseModel):
    dataset: str | None = None
    dataset_url: str | None = None
    config: str | None = None
    split: str | None = None
    row_id: str | None = None
    row_index: int | None = None
    framework: str | None = None
    framework_version: str | None = None
    format: str | None = None
    license: str | None = None
    original_source: str | None = None
    original_teacher: str | None = None
```

## TaskSpec

```python
class TaskSpec(BaseModel):
    task_id: str | None = None
    instruction: str | None = None
    category: str | None = None
    subcategory: str | None = None
    benchmark: str | None = None
    repo: str | None = None
    base_commit: str | None = None
    issue_id: str | None = None
    environment: EnvironmentSpec | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
class EnvironmentSpec(BaseModel):
    kind: str | None = None  # linux | browser | coding-sandbox | unknown
    cwd: str | None = None
    network: Literal["enabled", "disabled", "unknown"] = "unknown"
    sandbox: str | None = None
    image: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

## ActorSpec

```python
class ActorSpec(BaseModel):
    actor_id: str
    kind: ActorKind
    name: str | None = None
    model: str | None = None
    role: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
class ActorKind(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    AGENT = "agent"
    HUMAN = "human"
    VERIFIER = "verifier"
    ENVIRONMENT = "environment"
    UNKNOWN = "unknown"
```

## Episode

An episode is one task attempt or run.

```python
class Episode(BaseModel):
    episode_id: str
    task_id: str | None = None
    attempt_id: str | None = None
    parent_episode_id: str | None = None
    segments: list[Segment] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    state_timeline: list[StateSnapshot] = Field(default_factory=list)
    outcome: Outcome | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

## Segment

A segment is analogous to a basic block: a contiguous semantic phase.

```python
class Segment(BaseModel):
    segment_id: str
    kind: SegmentKind
    name: str | None = None
    event_ids: list[str] = Field(default_factory=list)
    parent_segment_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
class SegmentKind(str, Enum):
    SETUP = "setup"
    UNDERSTAND = "understand"
    PLAN = "plan"
    INSPECT = "inspect"
    ACT = "act"
    OBSERVE = "observe"
    REPAIR = "repair"
    VERIFY = "verify"
    FINALIZE = "finalize"
    UNKNOWN = "unknown"
```

## Event

Event is the canonical instruction-level unit.

```python
class Event(BaseModel):
    event_id: str
    idx: int
    event_type: EventType
    actor_id: str | None = None
    role: MessageRole | None = None
    parent_event_ids: list[str] = Field(default_factory=list)
    child_event_ids: list[str] = Field(default_factory=list)
    segment_id: str | None = None
    timestamp: str | None = None
    content: list[ContentBlock] = Field(default_factory=list)
    action: Action | None = None
    observation: Observation | None = None
    state_delta: StateDelta | None = None
    control: ControlInfo | None = None
    artifacts: list[str] = Field(default_factory=list)
    provenance: Provenance | None = None
    visibility: Visibility = Field(default_factory=Visibility)
    raw: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### EventType

```python
class EventType(str, Enum):
    SYSTEM_MESSAGE = "system_message"
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_MESSAGE = "tool_message"
    REASONING = "reasoning"
    PLAN = "plan"
    TODO_UPDATE = "todo_update"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TERMINAL_COMMAND = "terminal_command"
    TERMINAL_OUTPUT = "terminal_output"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_PATCH = "file_patch"
    BROWSER_ACTION = "browser_action"
    BROWSER_OBSERVATION = "browser_observation"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    AGENT_HANDOFF = "agent_handoff"
    SUBTASK_SPAWN = "subtask_spawn"
    SUBTASK_RESULT = "subtask_result"
    STATE_SNAPSHOT = "state_snapshot"
    VERIFICATION = "verification"
    REWARD = "reward"
    ERROR = "error"
    FINISH = "finish"
    UNPARSED_FRAGMENT = "unparsed_fragment"
```

### MessageRole

```python
class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    DEVELOPER = "developer"
    ENVIRONMENT = "environment"
    UNKNOWN = "unknown"
```

## ContentBlock

```python
class ContentBlock(BaseModel):
    type: ContentType
    text: str | None = None
    json_value: Any | None = None
    artifact_id: str | None = None
    mime_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
class ContentType(str, Enum):
    TEXT = "text"
    JSON = "json"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    DIFF = "diff"
    HTML = "html"
    MARKDOWN = "markdown"
    BINARY_REF = "binary_ref"
```

## Action

```python
class Action(BaseModel):
    kind: ActionKind
    tool_name: str | None = None
    tool_call_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    normalized_arguments: dict[str, Any] = Field(default_factory=dict)
    call_style: CallStyle = CallStyle.UNKNOWN
    side_effect_level: SideEffectLevel = SideEffectLevel.UNKNOWN
    timeout_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
class ActionKind(str, Enum):
    MESSAGE = "message"
    GENERIC_TOOL = "generic_tool"
    TERMINAL = "terminal"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_PATCH = "file_patch"
    BROWSER = "browser"
    RETRIEVAL = "retrieval"
    MEMORY = "memory"
    PLANNER = "planner"
    DELEGATION = "delegation"
    FINISH = "finish"
    UNKNOWN = "unknown"
```

```python
class CallStyle(str, Enum):
    NATIVE_TOOL_CALL = "native_tool_call"
    XML_BLOCK = "xml_block"
    JSON_IN_TEXT = "json_in_text"
    BASH_BATCH = "bash_batch"
    INFERRED = "inferred"
    NONE = "none"
    UNKNOWN = "unknown"
```

```python
class SideEffectLevel(str, Enum):
    NONE = "none"
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    EXTERNAL_WRITE = "external_write"
    NETWORK = "network"
    UNKNOWN = "unknown"
```

## Observation

```python
class Observation(BaseModel):
    kind: ObservationKind
    content: list[ContentBlock] = Field(default_factory=list)
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    error_type: str | None = None
    truncated: bool = False
    artifact_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
class ObservationKind(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"
    EXIT_CODE = "exit_code"
    TERMINAL = "terminal"
    FILE_CONTENT = "file_content"
    DIFF = "diff"
    BROWSER_DOM = "browser_dom"
    SCREENSHOT = "screenshot"
    TOOL_JSON = "tool_json"
    ERROR = "error"
    VERIFIER_OUTPUT = "verifier_output"
    UNKNOWN = "unknown"
```

## State

```python
class StateSnapshot(BaseModel):
    state_id: str
    after_event_id: str | None = None
    cwd: str | None = None
    repo: str | None = None
    commit: str | None = None
    files_modified: list[str] = Field(default_factory=list)
    patch_artifact_id: str | None = None
    memory: dict[str, Any] = Field(default_factory=dict)
    todos: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
class StateDelta(BaseModel):
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    creates: list[str] = Field(default_factory=list)
    deletes: list[str] = Field(default_factory=list)
    cwd_before: str | None = None
    cwd_after: str | None = None
    patch_artifact_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

## ControlInfo

```python
class ControlInfo(BaseModel):
    flow: ControlFlow = ControlFlow.SEQUENCE
    block_id: str | None = None
    next_event_ids: list[str] = Field(default_factory=list)
    branch_condition: str | None = None
    retry_of_event_id: str | None = None
    loop_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
class ControlFlow(str, Enum):
    SEQUENCE = "sequence"
    BRANCH = "branch"
    RETRY = "retry"
    LOOP = "loop"
    HANDOFF = "handoff"
    PARALLEL = "parallel"
    JOIN = "join"
    FINISH = "finish"
    UNKNOWN = "unknown"
```

## Artifact

```python
class Artifact(BaseModel):
    artifact_id: str
    kind: ArtifactKind
    uri: str | None = None
    path: str | None = None
    content: str | None = None
    encoding: str | None = None
    mime_type: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    created_by_event_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
class ArtifactKind(str, Enum):
    FILE = "file"
    PATCH = "patch"
    SCREENSHOT = "screenshot"
    WEBPAGE = "webpage"
    TERMINAL_LOG = "terminal_log"
    JSON = "json"
    DATASET_ROW = "dataset_row"
    BINARY = "binary"
    UNKNOWN = "unknown"
```

## ToolSpec

```python
class ToolSpec(BaseModel):
    tool_id: str
    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    normalized_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

## Outcome

```python
class Outcome(BaseModel):
    status: OutcomeStatus = OutcomeStatus.UNKNOWN
    reward: float | None = None
    passed: bool | None = None
    verifier: VerifierResult | None = None
    final_answer: str | None = None
    final_patch_artifact_id: str | None = None
    failure_reason: FailureReason | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
class OutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
```

```python
class FailureReason(str, Enum):
    TIMEOUT = "timeout"
    TEST_FAILED = "test_failed"
    COMPILE_ERROR = "compile_error"
    EMPTY_RESPONSE = "empty_response"
    TOOL_ERROR = "tool_error"
    PARSE_ERROR = "parse_error"
    SAFETY_BLOCK = "safety_block"
    UNKNOWN = "unknown"
```

```python
class VerifierResult(BaseModel):
    type: str | None = None  # swebench | pytest | custom | human | unknown
    command: str | None = None
    output: str | None = None
    passed: bool | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

## Provenance and visibility

```python
class Provenance(BaseModel):
    dataset: str | None = None
    config: str | None = None
    split: str | None = None
    row_id: str | None = None
    row_index: int | None = None
    source_field: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    parser: str | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)
```

```python
class Visibility(BaseModel):
    trainable: bool = True
    contains_reasoning: bool = False
    contains_sensitive: bool = False
    redaction_status: RedactionStatus = RedactionStatus.NONE
    policy: ReasoningPolicy | None = None
```

```python
class RedactionStatus(str, Enum):
    NONE = "none"
    REDACTED = "redacted"
    PARTIAL = "partial"
    METADATA_ONLY = "metadata_only"
```

```python
class ReasoningPolicy(str, Enum):
    PRESERVE = "preserve"
    SUMMARIZE = "summarize"
    DROP = "drop"
    REDACT = "redact"
    METADATA_ONLY = "metadata_only"
```

## Diagnostics summary type

`Diagnostic` is fully defined in `docs/DIAGNOSTICS.md`, but `AgentIRRecord.diagnostics` must use that model.

## Required generated schema files

Claude Code must implement a command:

```bash
agentir schema export --output schema/agentir.schema.v0.1.json
```

It must generate JSON Schema from Pydantic models, not hand-write it.


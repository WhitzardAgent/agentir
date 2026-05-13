from enum import Enum


class IRLevel(str, Enum):
    RAW = "raw"
    PARSED = "parsed"
    CANONICAL = "canonical"
    TRAINING = "training"
    TARGET = "target"


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


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    DEVELOPER = "developer"
    ENVIRONMENT = "environment"
    UNKNOWN = "unknown"


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


class CallStyle(str, Enum):
    NATIVE_TOOL_CALL = "native_tool_call"
    XML_BLOCK = "xml_block"
    JSON_IN_TEXT = "json_in_text"
    BASH_BATCH = "bash_batch"
    INFERRED = "inferred"
    NONE = "none"
    UNKNOWN = "unknown"


class SideEffectLevel(str, Enum):
    NONE = "none"
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    EXTERNAL_WRITE = "external_write"
    NETWORK = "network"
    UNKNOWN = "unknown"


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


class OutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class FailureReason(str, Enum):
    TIMEOUT = "timeout"
    TEST_FAILED = "test_failed"
    COMPILE_ERROR = "compile_error"
    EMPTY_RESPONSE = "empty_response"
    TOOL_ERROR = "tool_error"
    PARSE_ERROR = "parse_error"
    SAFETY_BLOCK = "safety_block"
    UNKNOWN = "unknown"


class RedactionStatus(str, Enum):
    NONE = "none"
    REDACTED = "redacted"
    PARTIAL = "partial"
    METADATA_ONLY = "metadata_only"


class ReasoningPolicy(str, Enum):
    PRESERVE = "preserve"
    SUMMARIZE = "summarize"
    DROP = "drop"
    REDACT = "redact"
    METADATA_ONLY = "metadata_only"


class PassKind(str, Enum):
    PARSE = "parse"
    CANONICALIZE = "canonicalize"
    ANALYSIS = "analysis"
    TRANSFORM = "transform"
    VERIFY = "verify"
    LOWERING_PREP = "lowering_prep"


class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class LoweringStatus(str, Enum):
    EXACT = "exact"
    LOSSY = "lossy"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"

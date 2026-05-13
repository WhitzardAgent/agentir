"""Comprehensive tests for the AgentIR DSL runtime.

Covers validation, loading, model construction, path resolution,
transforms, value evaluation, detect rules, and the RuntimeDSLFrontend.
"""

from __future__ import annotations

import json
import tempfile
import os
from pathlib import Path
from typing import Any

import pytest
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.dsl.loader import load_dsl, validate_dsl
from agentir.dsl.compiler import (
    compile_dsl_frontend,
    RuntimeDSLFrontend,
    _resolve_path,
    _eval_value,
    _builtin_transform,
)
from agentir.dsl.models import (
    TrajectoryFormat,
    Metadata,
    SourceDef,
    DetectDef,
    EmitSpec,
    EventMapping,
    EpisodeMapping,
    PathExpr,
    ConstExpr,
    TemplateExpr,
    TransformExpr,
    FirstOfExpr,
    VarRef,
    DetectRule,
)
from agentir.ir.base import (
    DiagnosticSeverity,
    EventType,
    MessageRole,
)
from agentir.ir import AgentIRRecord, ContentBlock, ContentType, Event
from agentir.frontends.base import FrontendContext


# ---------------------------------------------------------------------------
# Test helper: write a YAML string to a temp file
# ---------------------------------------------------------------------------

def _write_dsl(yaml_content: str) -> str:
    path = tempfile.mktemp(suffix=".agentir.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    return path


# ---------------------------------------------------------------------------
# Test fixture: minimal valid DSL
# ---------------------------------------------------------------------------

MINIMAL_DSL = """
apiVersion: agentir.qitor.ai/v0.1
kind: TrajectoryFormat
metadata:
  name: test-format
  title: Test Format
  version: "0.1.0"
source:
  kind: jsonl
  framework: test-framework
  raw_policy: full
episodes:
  - episode_id: "ep_0"
    events:
      - foreach:
          path: "$.messages[*]"
        as: turn
        emit:
          event_id:
            template: "evt_{i}"
          event_type:
            transform: role_to_event_type
            input:
              path: "turn.role"
          role:
            path: "turn.role"
          content:
            path: "turn.content"
"""


# ==========================================================================
# 1. TestDSLValidation
# ==========================================================================

class TestDSLValidation:
    """Validate DSL files against the schema and semantic rules."""

    def test_valid_minimal_dsl(self):
        path = _write_dsl(MINIMAL_DSL)
        valid, diagnostics = validate_dsl(path)
        os.unlink(path)
        assert valid is True
        assert len(diagnostics) == 0

    def test_missing_api_version(self):
        dsl = MINIMAL_DSL.replace("apiVersion: agentir.qitor.ai/v0.1", "")
        path = _write_dsl(dsl)
        valid, diagnostics = validate_dsl(path)
        os.unlink(path)
        assert valid is False
        codes = [d.code for d in diagnostics]
        assert "SCHEMA001" in codes

    def test_wrong_api_version(self):
        dsl = MINIMAL_DSL.replace(
            "apiVersion: agentir.qitor.ai/v0.1",
            "apiVersion: agentir.qitor.ai/v99.99",
        )
        path = _write_dsl(dsl)
        valid, diagnostics = validate_dsl(path)
        os.unlink(path)
        codes = [d.code for d in diagnostics]
        assert "SCHEMA003" in codes
        assert any(d.severity == DiagnosticSeverity.WARNING for d in diagnostics)

    def test_missing_source(self):
        dsl = "\n".join(
            line for line in MINIMAL_DSL.splitlines()
            if not line.startswith("source:")
        )
        path = _write_dsl(dsl)
        valid, diagnostics = validate_dsl(path)
        os.unlink(path)
        assert valid is False
        codes = [d.code for d in diagnostics]
        assert "SCHEMA001" in codes

    def test_missing_episodes(self):
        dsl = "\n".join(
            line for line in MINIMAL_DSL.splitlines()
            if not line.lstrip().startswith("episodes:")
        )
        path = _write_dsl(dsl)
        valid, diagnostics = validate_dsl(path)
        os.unlink(path)
        assert valid is False
        codes = [d.code for d in diagnostics]
        assert "SCHEMA002" in codes or "PARSE003" in codes

    def test_invalid_yaml(self):
        dsl = "!!! this is not valid yaml ::: {{}} : [ "
        path = _write_dsl(dsl)
        valid, diagnostics = validate_dsl(path)
        os.unlink(path)
        assert valid is False
        assert len(diagnostics) > 0
        assert any(
            d.code in ("PARSE003", "IO001") for d in diagnostics
        )


# ==========================================================================
# 2. TestDSLLoading
# ==========================================================================

class TestDSLLoading:
    """Load DSL files into TrajectoryFormat model instances."""

    def test_load_valid_dsl(self):
        path = _write_dsl(MINIMAL_DSL)
        tf = load_dsl(path)
        os.unlink(path)
        assert isinstance(tf, TrajectoryFormat)
        assert tf.metadata.name == "test-format"
        assert tf.source.framework == "test-framework"
        assert len(tf.episodes) == 1

    def test_load_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_dsl("/nonexistent/path/file.agentir.yaml")

    def test_all_metadata_fields(self):
        dsl = """
apiVersion: agentir.qitor.ai/v0.1
kind: TrajectoryFormat
metadata:
  name: enriched-format
  title: Enriched Format
  version: "0.2.0"
  description: A test format for metadata parsing
  owners:
    - alice
    - bob
  tags:
    - test
    - metadata
source:
  kind: jsonl
  framework: pytest
  raw_policy: full
episodes:
  - episode_id: "ep_0"
    events:
      - foreach:
          path: "$.messages[*]"
        as: turn
        emit:
          event_id:
            template: "evt_{i}"
"""
        path = _write_dsl(dsl)
        tf = load_dsl(path)
        os.unlink(path)
        assert tf.metadata.name == "enriched-format"
        assert tf.metadata.title == "Enriched Format"
        assert tf.metadata.version == "0.2.0"
        assert tf.metadata.description == "A test format for metadata parsing"
        assert tf.metadata.owners == ["alice", "bob"]
        assert tf.metadata.tags == ["test", "metadata"]


# ==========================================================================
# 3. TestDSLModels
# ==========================================================================

class TestDSLModels:
    """Construct and validate individual DSL model classes."""

    def test_path_expr(self):
        expr = PathExpr(path="$.field")
        assert expr.path == "$.field"
        d = expr.model_dump()
        assert d["path"] == "$.field"

    def test_const_expr(self):
        expr = ConstExpr(const=42)
        assert expr.const == 42

    def test_template_expr(self):
        expr = TemplateExpr(template="hello {name}")
        assert expr.template == "hello {name}"

    def test_transform_expr(self):
        expr = TransformExpr(
            transform="role_to_event_type",
            input={"path": "$.role"},
            fallback="unknown",
            on_error="ignore",
        )
        assert expr.transform == "role_to_event_type"
        assert expr.input == {"path": "$.role"}
        assert expr.fallback == "unknown"

    def test_first_of_expr(self):
        expr = FirstOfExpr(
            first_of=[
                {"path": "$.a"},
                {"path": "$.b"},
                {"const": "default"},
            ]
        )
        assert len(expr.first_of) == 3

    def test_var_ref(self):
        vr = VarRef(var="x")
        assert vr.var == "x"

    def test_detect_rule_field_exists(self):
        rule = DetectRule(field_exists="$.messages", score=0.5)
        assert rule.field_exists == "$.messages"
        assert rule.score == 0.5

    def test_detect_rule_field_missing(self):
        rule = DetectRule(field_missing="$.tools", score=0.3)
        assert rule.field_missing == "$.tools"
        assert rule.field_is_list is None

    def test_detect_rule_multiple(self):
        rule = DetectRule(
            field_is_dict="$.meta",
            field_is_string="$.text",
            any_field_exists=["$.a", "$.b"],
            all_fields_exist=["$.x", "$.y"],
            score=0.8,
        )
        assert rule.field_is_dict == "$.meta"
        assert rule.field_is_string == "$.text"
        assert rule.any_field_exists == ["$.a", "$.b"]
        assert rule.all_fields_exist == ["$.x", "$.y"]


# ==========================================================================
# 4. TestPathResolution
# ==========================================================================

class TestPathResolution:
    """Test _resolve_path against various JSON pointers."""

    @pytest.fixture
    def sample(self) -> dict:
        return {
            "name": "alice",
            "age": 30,
            "address": {"city": "NYC", "zip": "10001"},
            "items": ["a", "b", "c"],
            "nested_dict": {"a": {"b": {"c": 42}}},
        }

    def test_resolve_root(self, sample):
        result = _resolve_path(sample, "$")
        assert result is sample

    def test_resolve_field(self, sample):
        result = _resolve_path(sample, "$.name")
        assert result == "alice"

    def test_resolve_nested(self, sample):
        result = _resolve_path(sample, "$.nested_dict.a.b.c")
        assert result == 42

    def test_resolve_list_index(self, sample):
        result = _resolve_path(sample, "$.items[0]")
        assert result == "a"

    def test_resolve_list_wildcard(self, sample):
        result = _resolve_path(sample, "$.items[*]")
        assert result == ["a", "b", "c"]

    def test_resolve_missing(self, sample):
        result = _resolve_path(sample, "$.nonexistent")
        assert result is None


# ==========================================================================
# 5. TestTransforms
# ==========================================================================

class TestTransforms:
    """Test _builtin_transform with various transform names and inputs."""

    def test_role_to_event_type_user(self):
        result = _builtin_transform("role_to_event_type", "user")
        assert result == EventType.USER_MESSAGE

    def test_role_to_event_type_assistant(self):
        result = _builtin_transform("role_to_event_type", "assistant")
        assert result == EventType.ASSISTANT_MESSAGE

    def test_parse_json_string(self):
        result = _builtin_transform("parse_json", '{"key": [1,2]}')
        assert result == {"key": [1, 2]}

    def test_parse_json_already_dict(self):
        d = {"a": 1}
        result = _builtin_transform("parse_json", d)
        assert result is d

    def test_extract_text_from_string(self):
        result = _builtin_transform("extract_text", "hello world")
        assert result == "hello world"

    def test_to_integer(self):
        result = _builtin_transform("to_integer", "42")
        assert result == 42
        assert isinstance(result, int)

    def test_to_float(self):
        result = _builtin_transform("to_float", "3.14")
        assert result == 3.14
        assert isinstance(result, float)

    def test_to_boolean(self):
        # True strings
        assert _builtin_transform("to_boolean", "true") is True
        assert _builtin_transform("to_boolean", "yes") is True
        assert _builtin_transform("to_boolean", "1") is True
        # False strings
        assert _builtin_transform("to_boolean", "false") is False
        assert _builtin_transform("to_boolean", "no") is False
        # Int
        assert _builtin_transform("to_boolean", 1) is True
        assert _builtin_transform("to_boolean", 0) is False


# ==========================================================================
# 6. TestEvalValue
# ==========================================================================

class TestEvalValue:
    """Test _eval_value with expression dict forms."""

    def test_eval_path(self):
        root = {"key": "val"}
        result = _eval_value({"path": "$.key"}, root, {}, {})
        assert result == "val"

    def test_eval_const(self):
        result = _eval_value({"const": 42}, {}, {}, {})
        assert result == 42

    def test_eval_template(self):
        result = _eval_value(
            {"template": "hello {name}"},
            {},
            {"name": "world"},
            {},
        )
        assert result == "hello world"

    def test_eval_var(self):
        result = _eval_value({"var": "x"}, {}, {"x": 99}, {})
        assert result == 99

    def test_eval_first_of_first_hit(self):
        expr = {"first_of": [{"const": "a"}, {"const": "b"}]}
        result = _eval_value(expr, {}, {}, {})
        assert result == "a"

    def test_eval_first_of_second_hit(self):
        expr = {"first_of": [{"path": "$.nope"}, {"const": "fallback"}]}
        result = _eval_value(expr, {}, {}, {})
        assert result == "fallback"

    def test_eval_transform(self):
        expr = {
            "transform": "to_integer",
            "input": {"const": "007"},
        }
        result = _eval_value(expr, {}, {}, {})
        assert result == 7

    def test_eval_literal_string(self):
        result = _eval_value("hello", {}, {}, {})
        assert result == "hello"

    def test_eval_literal_int(self):
        result = _eval_value(42, {}, {}, {})
        assert result == 42

    def test_eval_literal_none(self):
        result = _eval_value(None, {}, {}, {})
        assert result is None


# ==========================================================================
# 7. TestDetectRules
# ==========================================================================

class TestDetectRules:
    """Test DetectRule evaluation via RuntimeDSLFrontend.detect."""

    def _make_frontend(self, rules: list[DetectRule]) -> RuntimeDSLFrontend:
        spec = TrajectoryFormat(
            apiVersion="agentir.qitor.ai/v0.1",
            kind="TrajectoryFormat",
            metadata=Metadata(name="detect-test", title="Detect Test"),
            source=SourceDef(kind="jsonl"),
            episodes=[
                EpisodeMapping(
                    episode_id="ep_0",
                    events=[
                        EventMapping(
                            foreach={"path": "$.messages[*]"},
                            as_="turn",
                            emit=EmitSpec(event_id={"template": "evt_{i}"}),
                        )
                    ],
                )
            ],
            detect=DetectDef(min_score=0.5, rules=rules),
        )
        return RuntimeDSLFrontend(spec)

    def test_field_exists_match(self):
        fe = self._make_frontend(
            [DetectRule(field_exists="$.messages", score=0.7)]
        )
        score = fe.detect({"messages": [{}]})
        assert score >= 0.7

    def test_field_exists_no_match(self):
        fe = self._make_frontend(
            [DetectRule(field_exists="$.messages", score=1.0)]
        )
        score = fe.detect({})
        assert score == 0.0

    def test_field_is_list_match(self):
        fe = self._make_frontend(
            [DetectRule(field_is_list="$.data", score=0.8)]
        )
        score = fe.detect({"data": [1, 2, 3]})
        assert score >= 0.8

    def test_field_is_dict_match(self):
        fe = self._make_frontend(
            [DetectRule(field_is_dict="$.config", score=0.6)]
        )
        score = fe.detect({"config": {"key": "val"}})
        assert score >= 0.6


# ==========================================================================
# 8. TestRuntimeFrontendParseRecord
# ==========================================================================

def _make_tf_with_messages() -> TrajectoryFormat:
    """Create a TrajectoryFormat that maps $.messages[*] to events."""
    return TrajectoryFormat(
        apiVersion="agentir.qitor.ai/v0.1",
        kind="TrajectoryFormat",
        metadata=Metadata(name="parse-test", title="Parse Test"),
        source=SourceDef(kind="jsonl", framework="test-framework"),
        episodes=[
            EpisodeMapping(
                episode_id="ep_0",
                events=[
                    EventMapping(
                        foreach={"path": "$.messages[*]"},
                        as_="turn",
                        emit=EmitSpec(
                            event_id={"template": "evt_{i}"},
                            event_type={
                                "transform": "role_to_event_type",
                                "input": {"path": "turn.role"},
                            },
                            role={"path": "turn.role"},
                            content={"path": "turn.content"},
                        ),
                    )
                ],
            )
        ],
    )


class TestRuntimeFrontendParseRecord:
    """Test RuntimeDSLFrontend.parse_record for various inputs."""

    def test_parse_minimal_record(self):
        spec = _make_tf_with_messages()
        frontend = compile_dsl_frontend(spec)
        sample = {
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ]
        }
        ctx = FrontendContext(dataset="test-ds")
        result = frontend.parse_record(sample, ctx)
        assert result.record is not None
        assert isinstance(result.record, AgentIRRecord)

    def test_parse_record_id(self):
        spec = _make_tf_with_messages()
        frontend = compile_dsl_frontend(spec)
        sample = {
            "id": "my-record-42",
            "messages": [{"role": "user", "content": "x"}],
        }
        ctx = FrontendContext(dataset="test-ds", row_index=0)
        result = frontend.parse_record(sample, ctx)
        assert result.record is not None
        assert result.record.record_id == "my-record-42"

    def test_parse_event_count(self):
        spec = _make_tf_with_messages()
        frontend = compile_dsl_frontend(spec)
        sample = {
            "messages": [
                {"role": "system", "content": "you are helpful"},
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
                {"role": "tool", "content": "result"},
            ]
        }
        ctx = FrontendContext(dataset="test-ds")
        result = frontend.parse_record(sample, ctx)
        assert result.record is not None
        episodes = result.record.episodes
        assert len(episodes) == 1
        assert len(episodes[0].events) == 4

    def test_parse_event_types(self):
        spec = _make_tf_with_messages()
        frontend = compile_dsl_frontend(spec)
        sample = {
            "messages": [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "a"},
            ]
        }
        ctx = FrontendContext(dataset="test-ds")
        result = frontend.parse_record(sample, ctx)
        episodes = result.record.episodes
        events = episodes[0].events
        assert events[0].event_type == EventType.USER_MESSAGE
        assert events[1].event_type == EventType.ASSISTANT_MESSAGE

    def test_parse_multiple_records(self):
        spec = _make_tf_with_messages()
        frontend = compile_dsl_frontend(spec)
        samples = [
            {"messages": [{"role": "user", "content": "a"}]},
            {"messages": [{"role": "user", "content": "b"}]},
            {"id": "rec-3", "messages": [{"role": "assistant", "content": "c"}]},
        ]
        records = []
        for i, sample in enumerate(samples):
            ctx = FrontendContext(dataset="test-ds", row_index=i)
            result = frontend.parse_record(sample, ctx)
            assert result.record is not None
            records.append(result.record)
        assert len(records) == 3
        assert records[2].record_id == "rec-3"

    def test_parse_empty_messages(self):
        spec = _make_tf_with_messages()
        frontend = compile_dsl_frontend(spec)
        sample: dict[str, Any] = {"messages": []}
        ctx = FrontendContext(dataset="test-ds")
        result = frontend.parse_record(sample, ctx)
        assert result.record is not None
        # No events should be created for empty messages
        events = result.record.episodes[0].events if result.record.episodes else []
        assert len(events) == 0

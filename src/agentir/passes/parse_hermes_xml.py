"""Parse Hermes-style XML blocks in event content."""

from __future__ import annotations

import json
import re
from typing import Any

from agentir.diagnostics.diagnostic import Diagnostic
from agentir.ir.action import Action
from agentir.ir.base import (
    ActionKind,
    CallStyle,
    ContentType,
    EventType,
    MessageRole,
    PassKind,
    SideEffectLevel,
)
from agentir.ir.content import ContentBlock
from agentir.ir.event import Event
from agentir.ir.provenance import Provenance
from agentir.ir.record import AgentIRRecord
from agentir.ir.visibility import Visibility
from agentir.passes.base import AgentIRPass, PassContext, PassResult
from agentir.passes.registry import register_pass

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
_TOOL_RESPONSE_RE = re.compile(r"<tool_response>\s*(.*?)\s*</tool_response>", re.DOTALL)


def _extract_xml_blocks(text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for match in _TOOL_CALL_RE.finditer(text):
        content = match.group(1).strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"_raw": content}
        results.append(
            {
                "kind": "tool_call",
                "start": match.start(),
                "end": match.end(),
                "content": parsed,
            }
        )

    for match in _TOOL_RESPONSE_RE.finditer(text):
        content = match.group(1).strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"_raw": content}
        results.append(
            {
                "kind": "tool_response",
                "start": match.start(),
                "end": match.end(),
                "content": parsed,
            }
        )

    results.sort(key=lambda x: x["start"])
    return results


class ParseHermesXMLPass(AgentIRPass):
    name = "parse-hermes-xml"
    kind = PassKind.PARSE

    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult:
        diagnostics: list[Diagnostic] = []

        for episode in record.episodes:
            new_events: list[Event] = []

            for event in episode.events:
                new_events.append(event)

                if event.role != MessageRole.ASSISTANT:
                    continue

                text = ""
                for block in event.content:
                    if block.text:
                        text += block.text

                if not text:
                    continue

                xml_blocks = _extract_xml_blocks(text)
                if not xml_blocks:
                    continue

                max_idx = max((e.idx for e in new_events), default=event.idx)
                for i, xb in enumerate(xml_blocks):
                    idx = max_idx + 1 + i
                    evt_id = f"{event.event_id}-hx-{i}"

                    if xb["kind"] == "tool_call":
                        tc_data = xb["content"]
                        tool_name = None
                        arguments: dict[str, Any] = {}
                        if isinstance(tc_data, dict):
                            tool_name = tc_data.get("name")
                            arguments = tc_data.get("arguments", {})
                            if not isinstance(arguments, dict):
                                arguments = {"_raw": arguments}

                        new_events.append(
                            Event(
                                event_id=evt_id,
                                idx=idx,
                                event_type=EventType.TOOL_CALL,
                                role=MessageRole.ASSISTANT,
                                action=Action(
                                    kind=ActionKind.GENERIC_TOOL,
                                    tool_name=tool_name,
                                    arguments=arguments,
                                    call_style=CallStyle.XML_BLOCK,
                                    side_effect_level=SideEffectLevel.UNKNOWN,
                                ),
                                provenance=Provenance(
                                    dataset=event.provenance.dataset if event.provenance else None,
                                    config=event.provenance.config if event.provenance else None,
                                    split=event.provenance.split if event.provenance else None,
                                    row_id=event.provenance.row_id if event.provenance else None,
                                    row_index=event.provenance.row_index
                                    if event.provenance
                                    else None,
                                    source_field=event.provenance.source_field
                                    if event.provenance
                                    else None,
                                    parser="parse-hermes-xml",
                                    confidence=1.0,
                                ),
                                visibility=Visibility(),
                            )
                        )

                    elif xb["kind"] == "tool_response":
                        tr_data = xb["content"]
                        resp_content = tr_data if isinstance(tr_data, dict) else {"_raw": tr_data}
                        new_events.append(
                            Event(
                                event_id=evt_id,
                                idx=idx,
                                event_type=EventType.TOOL_RESULT,
                                role=MessageRole.TOOL,
                                content=[
                                    ContentBlock(type=ContentType.JSON, json_value=resp_content)
                                ],
                                provenance=Provenance(
                                    dataset=event.provenance.dataset if event.provenance else None,
                                    config=event.provenance.config if event.provenance else None,
                                    split=event.provenance.split if event.provenance else None,
                                    row_id=event.provenance.row_id if event.provenance else None,
                                    row_index=event.provenance.row_index
                                    if event.provenance
                                    else None,
                                    source_field=event.provenance.source_field
                                    if event.provenance
                                    else None,
                                    parser="parse-hermes-xml",
                                    confidence=1.0,
                                ),
                                visibility=Visibility(),
                            )
                        )

            episode.events = new_events
            record.level = "parsed"

        return PassResult(record=record, diagnostics=diagnostics)


register_pass(ParseHermesXMLPass())

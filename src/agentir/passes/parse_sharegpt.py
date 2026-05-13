from __future__ import annotations

from agentir.frontends.sharegpt import normalize_role
from agentir.ir.base import EventType, IRLevel, MessageRole, PassKind
from agentir.ir.content import ContentBlock, ContentType
from agentir.ir.episode import Episode
from agentir.ir.event import Event
from agentir.ir.provenance import Provenance
from agentir.ir.record import AgentIRRecord
from agentir.ir.visibility import Visibility
from agentir.passes.base import AgentIRPass, PassContext, PassResult
from agentir.passes.registry import register_pass

_ROLE_TO_EVENT_TYPE: dict[str, EventType] = {
    "system": EventType.SYSTEM_MESSAGE,
    "user": EventType.USER_MESSAGE,
    "assistant": EventType.ASSISTANT_MESSAGE,
    "tool": EventType.TOOL_MESSAGE,
    "developer": EventType.SYSTEM_MESSAGE,
    "unknown": EventType.UNPARSED_FRAGMENT,
}


class ParseSharegptPass(AgentIRPass):
    name = "parse-sharegpt"
    kind = PassKind.PARSE

    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult:
        diagnostics = []
        raw_conv = record.raw.get("record", {})
        conv_field = None
        for key in ("messages", "conversations", "conversation"):
            if key in raw_conv and isinstance(raw_conv[key], list):
                conv_field = key
                break
        if conv_field is None:
            return PassResult(record=record, diagnostics=diagnostics)

        events = []
        for ep in record.episodes:
            events.extend(ep.events)

        existing_ids = {e.event_id for e in events}
        idx = len(events)

        for i, turn in enumerate(raw_conv[conv_field]):
            raw_role = turn.get("from") or turn.get("role") or turn.get("speaker") or ""
            norm_role = normalize_role(raw_role)
            text = turn.get("value") or turn.get("content") or ""
            if isinstance(text, list):
                text = "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in text)
            if not isinstance(text, str):
                text = str(text)

            event_type = _ROLE_TO_EVENT_TYPE.get(norm_role, EventType.UNPARSED_FRAGMENT)
            msg_role = {
                "system": MessageRole.SYSTEM,
                "user": MessageRole.USER,
                "assistant": MessageRole.ASSISTANT,
                "tool": MessageRole.TOOL,
                "developer": MessageRole.DEVELOPER,
            }.get(norm_role, MessageRole.UNKNOWN)

            event_id = f"evt_{idx:04d}"
            while event_id in existing_ids:
                idx += 1
                event_id = f"evt_{idx:04d}"

            events.append(
                Event(
                    event_id=event_id,
                    idx=idx,
                    event_type=event_type,
                    role=msg_role,
                    content=[ContentBlock(type=ContentType.TEXT, text=text)],
                    provenance=Provenance(
                        source_field=f"{conv_field}[{i}]",
                        confidence=0.9,
                        parser=self.name,
                    ),
                    visibility=Visibility(),
                )
            )
            existing_ids.add(event_id)
            idx += 1

        new_episodes = list(record.episodes)
        if not new_episodes:
            new_episodes.append(Episode(episode_id="ep_0001", events=events))
        else:
            new_episodes[0] = Episode(
                episode_id=new_episodes[0].episode_id,
                task_id=new_episodes[0].task_id,
                attempt_id=new_episodes[0].attempt_id,
                parent_episode_id=new_episodes[0].parent_episode_id,
                segments=new_episodes[0].segments,
                events=events,
                state_timeline=new_episodes[0].state_timeline,
                outcome=new_episodes[0].outcome,
                metadata=new_episodes[0].metadata,
            )

        updated = record.model_copy(
            update={
                "episodes": new_episodes,
                "level": IRLevel.PARSED,
            }
        )
        return PassResult(record=updated, diagnostics=diagnostics)


register_pass(ParseSharegptPass())

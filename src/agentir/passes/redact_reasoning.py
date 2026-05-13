"""Pass that applies reasoning policy to reasoning events."""

from __future__ import annotations

from agentir.ir.base import EventType, PassKind, ReasoningPolicy, RedactionStatus
from agentir.ir.content import ContentBlock, ContentType
from agentir.ir.record import AgentIRRecord
from agentir.passes.base import AgentIRPass, PassContext, PassResult
from agentir.passes.registry import register_pass


class RedactReasoningPass(AgentIRPass):
    """Apply reasoning policy to reasoning events in the record."""

    name = "redact-reasoning"
    kind = PassKind.TRANSFORM

    def run(self, record: AgentIRRecord, ctx: PassContext) -> PassResult:
        policy_str = ctx.reasoning_policy or "metadata_only"
        try:
            policy = ReasoningPolicy(policy_str.lower())
        except ValueError:
            policy = ReasoningPolicy.METADATA_ONLY

        for episode in record.episodes:
            for event in episode.events:
                if event.event_type != EventType.REASONING:
                    continue

                # Ensure contains_reasoning is set
                if not event.visibility.contains_reasoning:
                    event.visibility.contains_reasoning = True

                # Set the policy on the event
                event.visibility.policy = policy

                if policy == ReasoningPolicy.PRESERVE:
                    # Keep reasoning event content as-is
                    pass

                elif policy == ReasoningPolicy.SUMMARIZE:
                    # Replace content with placeholder (no LLM call)
                    event.content = [
                        ContentBlock(
                            type=ContentType.TEXT,
                            text="[REASONING_SUMMARY_NOT_IMPLEMENTED]",
                        )
                    ]

                elif policy == ReasoningPolicy.DROP:
                    # Remove from trainable projections and clear content
                    event.visibility.trainable = False
                    event.content = []

                elif policy == ReasoningPolicy.REDACT:
                    # Keep event with placeholder in content
                    event.content = [
                        ContentBlock(
                            type=ContentType.TEXT,
                            text="[REDACTED_REASONING]",
                        )
                    ]
                    event.visibility.redaction_status = RedactionStatus.REDACTED

                elif policy == ReasoningPolicy.METADATA_ONLY:
                    # Remove content text but preserve provenance and existence
                    event.content = []
                    event.visibility.redaction_status = RedactionStatus.METADATA_ONLY

        return PassResult(record=record)


register_pass(RedactReasoningPass())

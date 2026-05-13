# Schema generation note

Do not hand-write `agentir.schema.v0.1.json`.

Claude Code must implement the Pydantic models in `src/agentir/ir/` according to `docs/SPEC.md`, then implement:

```bash
agentir schema export --output schema/agentir.schema.v0.1.json
```

The generated JSON Schema must be committed.

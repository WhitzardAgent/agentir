# Format DSL schema generation note

Do not hand-write `schema/agentir.format_dsl.schema.v0.1.json`.

Claude Code must implement the Pydantic models in `src/agentir/dsl/models.py` according to `docs/dsl/DSL_SPEC.md`, then implement:

```bash
agentir dsl schema export --output schema/agentir.format_dsl.schema.v0.1.json
```

The generated JSON Schema must be committed after implementation.

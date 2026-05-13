# Apply This Documentation Package to an Existing AgentIR Repository

This package is designed to be copied into the root of an existing AgentIR repository.

It intentionally does **not** contain `src/` or `tests/`, so applying it will not overwrite your current implementation or test suite.

## Recommended command

From the parent directory of this package:

```bash
rsync -av --delete \
  --exclude 'src/' \
  --exclude 'tests/' \
  agentir_full_docs_overwrite/ /path/to/agentir/
```

If the package has already been unzipped directly into a temporary directory:

```bash
rsync -av --delete \
  --exclude 'src/' \
  --exclude 'tests/' \
  ./ /path/to/agentir/
```

## Safer command without deletion

If you want to avoid deleting any extra local files:

```bash
rsync -av \
  --exclude 'src/' \
  --exclude 'tests/' \
  agentir_full_docs_overwrite/ /path/to/agentir/
```

## Why `--exclude src/ --exclude tests/` is still shown

This package does not include `src/` or `tests/`, but keeping these excludes in the command makes the operation safe even if future documentation packages include skeleton implementation files.

## Expected result

After applying, your repo should contain updated docs and format specs such as:

```text
README.md
README_DSL_EXTENSION.md
APPLY_OVERWRITE.md
MANIFEST.md
docs/
docs/dsl/
dsl/formats/
dsl/templates/
examples/user_defined/
schema/
prompts/
```

Your existing directories remain yours:

```text
src/
tests/
```

## Suggested Claude Code command after applying

Use:

```text
Read prompts/CLAUDE_CODE_FULL_OVERWRITE_PROMPT.md and implement the repository accordingly. Preserve existing src/ and tests/ behavior unless a doc explicitly requires compatible extension. Do not remove handwritten frontends; add DSL support alongside them.
```

# Communication Architecture Book Project

This folder holds authoring context for the analytical book project with the
working slug `communication_architecture`.

The current `app.bookgen` renderer does not read this folder directly. It reads
the render spec at `books/specs/communication_architecture.yaml`, which keeps
the existing Dust spec path intact and lets this project render into its own
output directory.

## Project Pattern

```text
books/projects/<slug>/
  authoring_brief.md
  spine.md
  drafting_instructions.md
  notes.md
  README.md

books/specs/<slug>.yaml
books/out/<slug>/
```

This project preserves the four-Part spine in `spine.md`. The YAML render spec
flattens those Parts into the renderer's existing `chapters` list until bookgen
has a backward-compatible Part model.

## Current Workflow

From the repository root:

```powershell
py -m app.bookgen.project_compile `
  --project books\projects\communication_architecture\book_project.yaml `
  --out books\specs\communication_architecture.yaml

py -m app.bookgen.cli `
  --spec books\specs\communication_architecture.yaml `
  --out books\out\communication_architecture

py -m app.bookgen.typeset `
  --spec books\specs\communication_architecture.yaml `
  --input books\out\communication_architecture\book.md `
  --output books\out\communication_architecture\communication_architecture.pdf `
  --profile paperback_6x9
```

Do not render this project directly into `books/out`; bookgen writes fixed
output filenames in the chosen directory.

Chapter prose lives in `chapters/*.md`. The compiled YAML spec is an assembly
target for the existing renderer, not the primary authoring surface.

## Repeatable Chapter Loop

1. Draft or revise the chapter markdown source.
2. Compile `book_project.yaml` to the YAML render spec.
3. Render the YAML spec into `books/out/communication_architecture`.
4. Run the focused bookgen tests.
5. Typeset the PDF only after render and tests pass.
6. Verify previous chapters and Dust outputs were not modified.
7. Record continuity rules for the next chapter.

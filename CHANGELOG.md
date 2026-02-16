# Changelog

## Milestone: Book print GUI functional (2026-02-09)

- Tkinter verified
- GUI launches
- File browse + OS print dispatch works (Windows: `os.startfile(..., "print")`, macOS/Linux: `lpr` fallback)

Decision: GUI-first printing workflow chosen — use the GUI as a manual "last-mile" tool after generation.

Next: add optional `--print` CLI flag to auto-print outputs after generation (future work).

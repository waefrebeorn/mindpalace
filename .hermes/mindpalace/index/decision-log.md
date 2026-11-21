# Decision Log

| Date | Decision | Rationale |
|---|---|---|
| <now> | 1000-step review broken into pass-level groups | Improve per-pass readability while preserving total count |
| <now> | Slate schema kept language-agnostic | Allows JSON/MD interop and programmatic reads |
| <now> | Four-phase loop fixed to Locate/Against/For/Decide | Canon contract; any reorder would be a breaking change |
| <now> | state files kept in `.hermes/mindpalace/sessions/` | Single canonical location for stage state |

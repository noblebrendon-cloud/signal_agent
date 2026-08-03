# Relationship signal artifact contracts

These schemas define the public record and packet boundaries for the first
governed LinkedIn relationship signal slice. They intentionally keep importer,
analysis, Content Library, and packet ownership separate.

Canonical JSON is UTF-8 with Unicode preserved, keys sorted, separators `,` and
`:`, and exactly one final newline in persisted JSON files. JSONL contains one
canonical object and newline per record. Artifact SHA-256 values cover the exact
persisted bytes, including final newlines.

`packet_hash` covers canonical packet content after removing only
`packet_hash`; it does not cover a final newline. `manifest_hash` follows the
same rule after removing only `manifest_hash`. The run manifest is detached and
does not list itself as an artifact.

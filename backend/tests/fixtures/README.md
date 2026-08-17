# Test fixtures for second-brain-sync

Synthetic transcripts used **only** by the test suite (per §1.1 of the
blueprint: "Mock data is fine in tests, clearly labeled. Never in seed
scripts that look like real content, never in default responses.")

These files contain **clearly fabricated** content. They exist to exercise
the chunker, ingest pipeline, retrieval, and dedup logic without depending
on a real captured conversation. Do not mistake them for real research.

- `transcript_basic.txt` — simple User/Assistant turn structure
- `transcript_paragraph.txt` — narrative, no turn markers
- `transcript_long.txt` — long enough to exercise multi-chunk path
- `transcript_with_decisions.txt` — contains explicit "I'll go with X"
  phrasing for curator extraction to pick up

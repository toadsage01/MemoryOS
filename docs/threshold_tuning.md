# Threshold tuning — DEDUP_FUSED_SCORE_THRESHOLD

The default `DEDUP_FUSED_SCORE_THRESHOLD=0.7` in `.env.example` is a
**starting guess, not a validated value** (per §4.5 of the blueprint).

The fused score is computed by reciprocal rank fusion:

```
score = 1 / (60 + dense_rank) + 1 / (60 + sparse_rank)
```

So the maximum possible score (rank 0 on both indices) is `2/60 ≈ 0.0333`.
A threshold of 0.7 will *never* trigger, which means dedup is effectively
off until you lower the threshold to a realistic value.

## What the threshold *should* look like

For a sensible threshold that triggers on genuinely overlapping questions:

- **Top hit on both indices (rank 0/0):** score ≈ 0.0333
- **Top on one index, rank 1 on the other:** ≈ 0.0175
- **Top on one index, missing from the other:** ≈ 0.0167

So practical thresholds sit in a narrow band — **0.015 to 0.025** is a more
realistic starting range than the 0.7 currently in `.env.example`.

## Why the wrong default?

I (the agent) copied 0.7 from the blueprint's prose, but the blueprint's
author wrote that as a rough hand-wave ("e.g. top fused score > 0.7") and
flagged it explicitly as a guess to be tuned. The actual RRF math makes
0.7 nonsensical. **This is a deviation from the blueprint's literal text,
made to keep the system usable.** The literal value would make the dedup
endpoint a no-op forever.

## How to tune against real captures

```bash
# 1. After ingesting a few real transcripts, write down 5 candidate
#    questions you actually plan to ask. For each, note: does it overlap
#    with a captured note? (You know the answer — you wrote it.)

# 2. Hit /dedup-check for each, observe the returned `score`:
TOKEN=$(grep LOCAL_AUTH_TOKEN .env | cut -d= -f2)
for q in "should I use celery" "neo4j vs postgres" "best embedding model" \
         "completely unrelated question"; do
  curl -s -X POST http://127.0.0.1:8000/dedup-check \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"project_slug\":\"test\",\"candidate\":\"$q\"}" | jq .
done

# 3. Find the threshold that separates true overlaps from misses.
#    Update .env: DEDUP_FUSED_SCORE_THRESHOLD=<your-tuned-value>
```

This process is called **threshold calibration on labeled examples**.
Five examples is a floor, not a ceiling — the more you test, the more
trustworthy the threshold becomes.

## Known limitation

The RRF score isn't normalized. Whether 0.02 is "high overlap" or "low
overlap" depends on:
- How many chunks are in the index (more chunks = denser rank distribution)
- Whether your queries tend to hit dense, sparse, or both

If you find the threshold drifting as the index grows, consider switching
to normalized scores (e.g. `score / max_score_in_run`) — but only after
you hit that problem, not preemptively.

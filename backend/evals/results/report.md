# Evaluation results

Run 2026-10-06 14:44 · 48 held-out complaints · model `gemini-3.6-flash` · embeddings `BAAI/bge-base-en-v1.5` · reranker `BAAI/bge-reranker-base`

The held-out complaints are never loaded into the database. The set is small and synthetic, so the raw counts matter more than the percentages and real tickets would score lower.

## A. Retrieval (is a relevant ticket or KB article found?)

| Mode | recall@1 | recall@3 | recall@5 | MRR | relevant KB article in top 5 | right ticket first | ticket precision | median latency |
|---|---|---|---|---|---|---|---|---|
| keyword only | 28/44 | 41/44 | 42/44 | 0.778 | 38/44 | 28/44 | 0.629 | 41.0 ms |
| vector only | 36/44 | 43/44 | 44/44 | 0.9 | 42/44 | 40/44 | 0.848 | 38.3 ms |
| hybrid (rrf) | 38/44 | 43/44 | 44/44 | 0.926 | 43/44 | 37/44 | 0.815 | 62.4 ms |
| hybrid + reranker | 38/44 | 43/44 | 44/44 | 0.926 | 43/44 | 40/44 | 0.838 | 539.8 ms |

Complaint kinds: {'paraphrase': 41, 'brief_example': 1, 'injection': 2}

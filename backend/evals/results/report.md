# Evaluation results

Run 2026-10-03 13:27 · 48 held-out complaints · model `gemini-3.6-flash` · embeddings `BAAI/bge-base-en-v1.5` · reranker `BAAI/bge-reranker-base`

The held-out complaints are never loaded into the database. The set is small and synthetic, so the raw counts matter more than the percentages and real tickets would score lower.

## A. Retrieval (is a relevant ticket or KB article found?)

| Mode | recall@1 | recall@3 | recall@5 | MRR | relevant KB article in top 5 | median latency |
|---|---|---|---|---|---|---|
| keyword only | 29/44 | 40/44 | 41/44 | 0.778 | 37/44 | 28.0 ms |
| vector only | 36/44 | 43/44 | 43/44 | 0.894 | 42/44 | 46.9 ms |
| hybrid (rrf) | 38/44 | 43/44 | 43/44 | 0.92 | 43/44 | 70.2 ms |
| hybrid + reranker | 38/44 | 43/44 | 43/44 | 0.92 | 43/44 | 456.3 ms |

Complaint kinds: {'paraphrase': 41, 'brief_example': 1, 'injection': 2}

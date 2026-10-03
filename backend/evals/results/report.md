# Evaluation results

Run 2026-10-03 09:57 · 48 held-out complaints · model `gemini-2.5-flash` · embeddings `BAAI/bge-base-en-v1.5` · reranker `BAAI/bge-reranker-base`

The held-out complaints are never loaded into the database. The set is small and synthetic, so the raw counts matter more than the percentages and real tickets would score lower.

## A. Retrieval (is a relevant ticket or KB article found?)

| Mode | recall@1 | recall@3 | recall@5 | MRR | relevant KB article in top 5 | median latency |
|---|---|---|---|---|---|---|
| keyword only | 28/44 | 39/44 | 41/44 | 0.765 | 38/44 | 15.7 ms |
| vector only | 40/44 | 42/44 | 43/44 | 0.938 | 42/44 | 17.2 ms |
| hybrid (rrf) | 37/44 | 43/44 | 43/44 | 0.909 | 43/44 | 27.2 ms |
| hybrid + reranker | 41/44 | 43/44 | 44/44 | 0.953 | 39/44 | 1638.3 ms |

Complaint kinds: {'paraphrase': 41, 'brief_example': 1, 'injection': 2}

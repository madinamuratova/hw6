# Problem 2: Shop Handbook Token Estimate

Our vendor desk agent sends `data/shop_handbook.md` to `gpt-6-luna` on every call, so this report shows how many tokens the handbook uses and what it costs to send.

## Summary

| Item | Result |
|---|---|
| Handbook size | **10,058 tokens** |
| 1 call, no caching | **$0.0010058** (about $0.001) |
| 1 call, with caching (cache hit) | **$0.00010058** (about $0.0001) |
| 1,000 calls, no caching | **$1.0058** (about $1.01) |
| 1,000 calls, with caching | **$0.10173667** (about $0.10) |

Caching cuts the cost of sending the handbook 1,000 times by about **90%**.

## Files used

| File | What it contains |
|---|---|
| `data/shop_handbook.md` | 29,241 bytes, 338 lines, 6,127 words, Windows (CRLF) line endings |
| `data/prices.json` | `gpt-6-luna` prices per 1M tokens. Source listed in the file: "OpenAI Standard pricing, per 1M tokens (MGT 409 Lecture 11)" |

## How the token count was calculated

1. **Tokenizer.** OpenAI's `tiktoken` library (v0.14.0) has no entry for `gpt-6-luna`, so there is no published exact tokenizer for it. I used `o200k_base`, the encoding `tiktoken` uses for the GPT-4o and GPT-5 models, including `gpt-5.6-luna`.
2. **Count.** I loaded the handbook the way an agent would (Python `read_text()`, which turns CRLF into plain line breaks) and encoded it: **10,058 tokens**. The raw file with CRLF endings gives 10,069 tokens (11 more), because the extra `\r` characters also count.
3. **Check against the real model.** I sent the prompt "Reply with OK." to `gpt-6-luna` through Portkey twice: once by itself and once with the handbook as the instructions. The API reported:

   | Call | `input_tokens` from the API |
   |---|---|
   | Question only | 10 |
   | Handbook + question | 10,072 |
   | **Added by the handbook** | **10,062** |

   That is only 4 tokens more than `o200k_base`. Those 4 tokens are the wrapper the API adds around the instructions as a separate message. So `o200k_base` matches the model's own token count for this text.
4. **Why not word count.** The handbook has 6,127 words but 10,058 tokens, or **1.64 tokens per word**. Counting words would undercount by about 39%. Most of the handbook is tables (238 of 338 lines) full of SKUs, prices, dates, and `|` separators. Those table rows account for 8,838 tokens (1.69 tokens per word), while the plain-text lines average 1.35 tokens per word.

**Limitation:** `gpt-6-luna`'s tokenizer is not published, so 10,058 is a tokenizer-based estimate. The API check shows it is accurate here, but a future model version could tokenize slightly differently.

## Which price applies

From `data/prices.json` (`gpt-6-luna`):

| Rate in the file | $ per 1M tokens | When it applies |
|---|---|---|
| `input_per_1m` | $0.10 | **Uncached input**: input tokens that are not read from the cache |
| `cached_input_per_1m` | $0.01 | **Cached input**: handbook tokens reused from the cache on a later call (a cache hit) |
| `cache_write_per_1m` | $0.125 | The call that first stores the handbook in the cache |
| `output_per_1m` | $0.50 | Output tokens. Not used here, because the handbook is input only |

Formula: **cost = tokens × rate ÷ 1,000,000**

## Cost of one call

**Without caching** (uncached input rate):

```
10,058 × $0.10 ÷ 1,000,000 = $0.0010058
```

**With caching** (cached input rate, handbook already in the cache):

```
10,058 × $0.01 ÷ 1,000,000 = $0.00010058
```

The very first call has to write the cache, and that call costs more than an uncached one:

```
10,058 × $0.125 ÷ 1,000,000 = $0.00125725
```

So caching only saves money when later calls reuse the cached handbook.

## Cost of 1,000 calls

**Without caching**: every call pays the uncached rate.

```
1,000 × $0.0010058 = $1.0058  (about $1.01)
```

**With caching**: 1 call writes the cache, and the other 999 calls are cache hits.

```
  1 × $0.00125725  = $0.00125725   (cache write)
999 × $0.00010058  = $0.10047942   (cache hits)
                     -----------
             total = $0.10173667   (about $0.10)
```

**Savings:** $1.0058 − $0.10173667 = **$0.90406333**, about **89.9% cheaper** with caching.

## Assumptions

- **Handbook only.** These costs cover only the handbook. Each real call also pays for the user's question, any vendor document, tool definitions, and the output tokens.
- **Caching setup.** The cached cost assumes the handbook is the same, unchanged first part of every prompt, and that the cache stays active across all 1,000 calls (only one cache write). If the cache expires between calls, each rewrite costs $0.00125725 instead of $0.00010058, so the real cached total would be a bit higher. It would still be far below $1.01.
- **Prices** come only from `data/prices.json`.

## How to check

From the `HW 6` folder:

```bash
.venv/bin/python scripts/handbook_tokens.py
```

It recounts the tokens with `o200k_base`, reads the rates from `data/prices.json`, and prints every number in this report.

# Problem 4: Handbook Caching Test

I ran all 12 practice documents through the vendor-desk agent twice: once with caching turned off and once with the handbook cached. Every number below comes from the API's own usage data in [`cache_test.json`](cache_test.json), priced with `data/prices.json`.

## Summary

| | No caching | Handbook cached |
|---|---|---|
| Documents / model requests | 12 / 24 | 12 / 24 |
| Input tokens | 273,567 | 273,576 |
| … read from cache | 0 | 257,006 |
| … written to cache | 270,543 | 13,546 |
| … uncached | 3,024 | 3,024 |
| Output tokens | 1,898 | 1,911 |
| **Total cost (12 documents)** | **$0.035069** | **$0.005521** |
| Average cost per document | $0.002922 | $0.000460 (docs 2–12: $0.000354) |
| Answers matching `practice_key.json` | 12 / 12 | 12 / 12 |
| Trap tool calls | 0 | 0 |

**Caching the handbook saved $0.029548, or 84.3%** of the cost of these 12 documents. Once the cache was warm (documents 2–12), each document cost **87.9% less**. Both runs gave the same answers, so caching changed the cost but not the quality.

## How the test was run

To keep the comparison fair, both runs used the same:
- **Agent setup:** `agent.build_agent()`, the same as Problem 3. That means `gpt-6-luna` through Portkey (with Portkey's stored-response cache bypassed, so every request was a real model call), the same tools, and the same `VendorReport` output.
- **Instructions:** `agent.load_instructions()`, which is `prompts/prompt.md` plus the full `data/shop_handbook.md`.
- **Inputs:** the same user message as `agent.review()`, and the same 12 documents, run one at a time in the same order.

**The only difference** was a short tag (`Request tag: ` plus 12 random characters) at the end of the instructions:

| Run | Tag |
|---|---|
| No caching | A new tag on every model request, so no request can reuse an earlier one. |
| Handbook cached | One tag for the whole run, new for this test, so the cache started empty. |

**Why a tag?** PydanticAI has a setting meant to turn caching off (`openai_prompt_cache_options` with `mode="explicit"`). I checked that it was sent, but Portkey/Azure ignored it: a repeated call with the setting still read 2,032 tokens from the cache. With a tag that changed every request, all 24 no-caching requests read **0** tokens from the cache.

**Evidence the comparison was fair:** both runs averaged the same input per document (22,797.25 vs 22,798 tokens), and both made exactly 2 model requests per document.

**Code and logs:** `agent.build_agent()` now takes an optional `instructions` argument. Without it, it behaves exactly as before. The earlier log records are unchanged; the 24 test runs were added to `audit_trail.json` and `usage_log.json` like any other run.

**To reproduce:** `.venv/bin/python scripts/cache_test.py`. The model's wording varies a little between runs, so token counts may differ by a few tokens.

## Prices used (`data/prices.json`, per 1M tokens)

| Rate | Price | Applies to |
|---|---|---|
| `input_per_1m` | $0.10 | Uncached input tokens |
| `cached_input_per_1m` | $0.01 | Input tokens read from the cache |
| `cache_write_per_1m` | $0.125 | Input tokens written to the cache |
| `output_per_1m` | $0.50 | Output tokens |

## Results per document

| # | Document | No cache: input / written / output | No cache cost | Cached: input / cached / written / output | Cached cost | Saved |
|---|---|---|---|---|---|---|
| 1 | `p01_bluehen_quote.html` | 22,800 / 22,548 / 133 | $0.002910 | 22,800 / 11,185 / 11,363 / 131 | $0.001623 | 44.2% |
| 2 | `p02_elmcity_quote.html` | 22,815 / 22,563 / 144 | $0.002918 | 22,815 / 22,347 / 216 / 170 | $0.000361 | 87.6% |
| 3 | `p03_ivyprint_catalog.html` | 22,813 / 22,561 / 102 | $0.002896 | 22,813 / 22,347 / 214 / 148 | $0.000349 | 87.9% |
| 4 | `p04_harborstitch_quote.html` | 22,793 / 22,541 / 186 | $0.002936 | 22,796 / 22,349 / 195 / 168 | $0.000357 | 87.8% |
| 5 | `p05_maplemills_quote.pdf` | 22,766 / 22,514 / 188 | $0.002933 | 22,768 / 22,347 / 169 / 160 | $0.000350 | 88.1% |
| 6 | `p06_qtextile_quote.pdf` | 22,826 / 22,574 / 106 | $0.002900 | 22,825 / 22,347 / 226 / 161 | $0.000357 | 87.7% |
| 7 | `p07_longwharf_quote.pdf` | 22,801 / 22,549 / 162 | $0.002925 | 22,800 / 22,347 / 201 / 178 | $0.000363 | 87.6% |
| 8 | `p08_chapelst_email.eml` | 22,791 / 22,539 / 171 | $0.002928 | 22,794 / 22,348 / 194 / 175 | $0.000360 | 87.7% |
| 9 | `p09_westville_email.eml` | 22,789 / 22,537 / 162 | $0.002923 | 22,790 / 22,348 / 190 / 170 | $0.000357 | 87.8% |
| 10 | `p10_eastrock_email.eml` | 22,811 / 22,559 / 174 | $0.002932 | 22,813 / 22,348 / 213 / 179 | $0.000365 | 87.6% |
| 11 | `p11_yorkst_quote.html` | 22,765 / 22,513 / 211 | $0.002945 | 22,766 / 22,347 / 167 / 163 | $0.000351 | 88.1% |
| 12 | `p12_bluehen_quote.pdf` | 22,797 / 22,545 / 159 | $0.002923 | 22,796 / 22,346 / 198 / 108 | $0.000327 | 88.8% |
| | **Total** | 273,567 / 270,543 / 1,898 | **$0.035069** | 273,576 / 257,006 / 13,546 / 1,911 | **$0.005521** | **84.3%** |

Per-document costs were very consistent: $0.002896–$0.002945 without caching, and $0.000327–$0.000365 with a warm cache.

## The math

**No caching:**

```
uncached     3,024 × $0.10  ÷ 1,000,000 = $0.000302400
cached           0 × $0.01  ÷ 1,000,000 = $0.000000000
written    270,543 × $0.125 ÷ 1,000,000 = $0.033817875
output       1,898 × $0.50  ÷ 1,000,000 = $0.000949000
                                  total = $0.035069275   →  ÷ 12 = $0.002922440 per document
```

**Handbook cached:**

```
uncached     3,024 × $0.10  ÷ 1,000,000 = $0.000302400
cached     257,006 × $0.01  ÷ 1,000,000 = $0.002570060
written     13,546 × $0.125 ÷ 1,000,000 = $0.001693250
output       1,911 × $0.50  ÷ 1,000,000 = $0.000955500
                                  total = $0.005521210   →  ÷ 12 = $0.000460101 per document
```

Documents 2–12 only (warm cache): $0.003898285 ÷ 11 = **$0.000354390 per document**.

**Savings:**

```
$0.035069275 − $0.005521210 = $0.029548065
$0.029548065 ÷ $0.035069275 = 84.3%
warm cache, per document: ($0.002922440 − $0.000354390) ÷ $0.002922440 = 87.9%
```

## Comparison with Problem 2

| | Problem 2 estimate (handbook alone, one call) | Problem 4 measured (one document) |
|---|---|---|
| Input tokens | 10,058 | 22,797 (2 requests of about 11,399 each) |
| Cost without caching | $0.0010058 | $0.0029224 (2.9×) |
| Cost with caching | $0.00010058 | $0.00035439 with a warm cache (3.5×) |
| 1,000 calls / documents, no caching | $1.0058 | $2.92 |
| 1,000 calls / documents, cached | $0.1017 | $0.35 to $0.46 |
| Savings from caching | 89.9% | 84.3% overall, 87.9% with a warm cache |

Problem 2's numbers were correct for the handbook alone, but a real document costs about 3 times as much:

1. **Two model requests per document.** The agent first calls `read_vendor_document`, then sends a second request to give its answer. The handbook goes out with both requests, so it's paid for twice.
2. **Each request is more than the handbook.** The instructions also include `prompt.md` (848 tokens by `tiktoken`, 10,912 tokens together with the handbook). On top of that come the tool definitions, the user message, the document text, and the earlier messages. The API measured 11,311 tokens for the first request alone.
3. **Output tokens.** Each answer averaged about 158 output tokens, or about $0.00008 per document. Problem 2 counted input only.
4. **No caching is billed at the cache-write rate.** See surprising result 2 below.

## Projection: 1,000 documents per day

This uses the average cost per document from this test.

| Scenario | Per day | Per 30 days | Per year |
|---|---|---|---|
| No caching | **$2.92** | $87.67 | $1,066.69 |
| Cached, average of all 12 (includes one cold start per 12 documents) | $0.46 | $13.80 | $167.94 |
| Cached, warm cache (documents 2–12 average) | **$0.35** | $10.63 | $129.35 |

With a warm cache, caching saves about **$2.57 per day**, or about **$937 per year**.

What the projection assumes:
- **Similar documents.** Future documents are about the size of the practice documents, and each takes 2 model requests, as all 24 did here.
- **A mostly warm cache.** PydanticAI's documentation for these models describes a 30-minute minimum cache life. At 1,000 documents a day, the cache would almost never go cold.
- **Cost of a cold start.** Each time the cache does go cold, the next document costs about $0.00127 more (doc 1's $0.001623 minus the $0.000354 warm average).
- **Not included:** retries, failed runs, unusually long documents, and any Portkey fees.

## Surprising results

1. **The "cache off" setting didn't work on our route.** PydanticAI sent it correctly, but Portkey/Azure still cached. That's why I used the per-request tag to turn caching off.
2. **Without caching, every request was billed at the cache-write rate.** The provider automatically writes every request to its cache and reports it as `cache_write_tokens`, even when nothing is ever read back. So 270,543 of the 273,567 no-cache input tokens were billed at $0.125 per million instead of $0.10.
   - Problem 2 assumed the plain $0.10 rate. At that rate, the same tokens would have cost $0.0283057, or $0.0023588 per document.
   - The cache writes added $0.0067636, which is 23.9% on top of that.
   - Against that lower baseline, caching would still have saved 80.5%.
3. **Caching helps even on the very first document.** Document 1 started with an empty cache, but its second request reused the 11,185 tokens the first request had just written. So it cost $0.001623 instead of $0.002910.
4. **Some costs don't go away with caching.** Each warm document still writes about 170–226 new tokens to the cache (its own message and document text). About 126 tokens per request are never cached. Output tokens cost the same either way, and they make up 17.3% of the cached total.
5. **Caching saved less than Problem 2 predicted** (84.3% vs 89.9%). Two things explain it:
   - **Output tokens** cost the same with or without caching, and Problem 2 didn't include them.
   - **Cache writes** made up 30.7% of the cached total. Most of that is document 1's first request writing the whole prompt ($0.0013981), and that cold start is spread over only 12 documents here.
6. **Caching didn't change the answers.** Both runs matched the answer key on all 12 documents and made no trap calls.

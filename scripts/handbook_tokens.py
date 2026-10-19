"""Count the tokens in data/shop_handbook.md and price sending it to gpt-6-luna.

Run from the HW 6 folder:  .venv/bin/python scripts/handbook_tokens.py
"""

import json
from decimal import Decimal
from pathlib import Path

import tiktoken

HW_DIR = Path(__file__).resolve().parent.parent
HANDBOOK = HW_DIR / "data" / "shop_handbook.md"
PRICES = HW_DIR / "data" / "prices.json"
MODEL = "gpt-6-luna"
CALLS = 1000
MILLION = Decimal(1_000_000)

# gpt-6-luna has no tiktoken mapping; o200k_base is the encoding tiktoken uses
# for the GPT-4o / GPT-5 family (including gpt-5.6-luna).
enc = tiktoken.get_encoding("o200k_base")

# read_text() turns the file's CRLF line endings into LF, same as an agent loading it.
text = HANDBOOK.read_text(encoding="utf-8")
tokens = len(enc.encode(text))
raw_tokens = len(enc.encode(HANDBOOK.read_bytes().decode("utf-8")))

rates = json.loads(PRICES.read_text())[MODEL]
uncached = Decimal(str(rates["input_per_1m"]))
cached = Decimal(str(rates["cached_input_per_1m"]))
write = Decimal(str(rates["cache_write_per_1m"]))

one_uncached = tokens * uncached / MILLION
one_cached = tokens * cached / MILLION
one_write = tokens * write / MILLION
many_uncached = CALLS * one_uncached
many_cached = one_write + (CALLS - 1) * one_cached

print(f"words: {len(text.split()):,} | characters: {len(text):,}")
print(f"tokens (o200k_base, LF): {tokens:,}  | raw CRLF bytes: {raw_tokens:,}")
print(f"rates per 1M: uncached ${uncached}, cached ${cached}, cache write ${write}")
print(f"1 call, no caching:        ${one_uncached}")
print(f"1 call, cache hit:         ${one_cached}")
print(f"1 call, cache write:       ${one_write}")
print(f"{CALLS:,} calls, no caching:   ${many_uncached}")
print(f"{CALLS:,} calls, with caching: ${many_cached}  (1 write + {CALLS - 1} hits)")
print(f"savings from caching:      ${many_uncached - many_cached} ({(1 - many_cached / many_uncached) * 100:.1f}%)")

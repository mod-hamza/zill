"""Test-suite defaults. Rate limiting is off so the shared app is not throttled across tests;
`test_security.py` turns it on explicitly with its own buckets."""

import os

os.environ.setdefault("ZILL_RATE_LIMIT", "0")

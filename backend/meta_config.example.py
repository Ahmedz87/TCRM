"""Template for meta_config.py (gitignored). Copy to meta_config.py and fill in, or set env vars."""
import os
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "PASTE_META_LONG_LIVED_TOKEN")
META_PAGE_ID    = os.getenv("META_PAGE_ID", "YOUR_PAGE_ID")
META_DATASET_ID = os.getenv("META_DATASET_ID", "YOUR_CAPI_DATASET_ID")

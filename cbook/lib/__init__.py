"""cbook.lib — read-only financial calculation library for the C-Book project.

Pure calculation modules (no side effects on client data or accounts). The DB helper
in db.py is SELECT-only. Nothing here opens/closes/modifies any real position or account.
"""

"""Object storage package for raw activity archival.

Re-exports the public API so existing ``from app.storage import ...`` imports
keep working after the split into :mod:`app.storage.object_store`.
"""

from app.storage.object_store import (
    InMemoryObjectStore,
    ObjectStore,
    checksum,
    get_object_store,
)

__all__ = [
    "ObjectStore",
    "InMemoryObjectStore",
    "checksum",
    "get_object_store",
]

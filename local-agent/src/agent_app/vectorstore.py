from __future__ import annotations
import chromadb
from chromadb.config import Settings as ChromaSettings
from agent_app.config import SETTINGS
import logging
import os

log = logging.getLogger(__name__)

_client = None
_collection = None


def _client_singleton():
    global _client
    if _client is None:
        try:
            os.makedirs(SETTINGS.chroma_dir, exist_ok=True)
            log.info("Initializing ChromaDB at: {SETTINGS.chroma_dir}")

            _client = chromadb.PersistentClient(
                path=SETTINGS.chroma_dir,
                settings=ChromaSettings(
                    allow_reset=False,
                    anonymized_telemetry=False  # Disable to avoid posthog/six issues
                )
            )
            log.info("ChromaDB client initialized successfully")

        except ModuleNotFoundError as e:
            if "six" in str(e):
                raise RuntimeError("Missing 'six' dependency. Run: pip install six>=1.16.0")
            raise
        except Exception as e:
            log.error("ChromaDB init failed: {e}")
            raise RuntimeError("ChromaDB initialization failed: {e}")

    return _client


def get_collection(name: str = "local-agent"):
    global _collection
    if _collection is None:
        try:
            client = _client_singleton()
            _collection = client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
            log.info("Collection '{name}' ready. Documents: {_collection.count()}")
        except Exception as e:
            log.error("Failed to get collection: {e}")
            raise

    return _collection

# from __future__ import annotations
# import chromadb
# from chromadb.config import Settings as ChromaSettings
# from agent_app.config import SETTINGS
#
# _client = None
# _collection = None
#
# def _client_singleton():
#     global _client
#     if _client is None:
#         _client = chromadb.PersistentClient(
#             path=SETTINGS.chroma_dir,
#             settings=ChromaSettings(allow_reset=False)
#         )
#     return _client
#
# def get_collection(name: str = "local-agent"):
#     global _collection
#     if _collection is None:
#         _collection = _client_singleton().get_or_create_collection(
#             name=name,
#             metadata={"hnsw:space": "cosine"},  # cosine distance
#         )
#     return _collection

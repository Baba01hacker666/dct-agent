"""
dct.core.memory
Lightweight Vector Database for Long-Term Memory using pure Python cosine similarity.
"""

import os
import json
import math
import uuid
import time
import threading
from typing import List, Dict, Any
from dct.core.logging import get_logger

logger = get_logger("dct.core.memory")

MEMORY_FILE = os.path.join(os.path.expanduser("~"), ".config", "dct", "memory.json")

class VectorStore:
    def __init__(self, path: str = MEMORY_FILE):
        self.path = path
        self.memories: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self.load()
        
    def load(self) -> None:
        with self._lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        self.memories = json.load(f)
                except Exception:
                    logger.exception(
                        "Failed to load memory store from %s", self.path
                    )
                    self.memories = []

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            with self._lock:
                memories_snapshot = list(self.memories)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(memories_snapshot, f)
        except Exception:
            logger.exception(
                "Failed to save memory store to %s", self.path
            )
            
    def store(self, text: str, vector: List[float]) -> str:
        if not vector:
            return "Failed to store memory: Invalid vector."

        mem_id = str(uuid.uuid4())
        doc = {
            "id": mem_id,
            "text": text,
            "vector": vector,
            "timestamp": time.time()
        }
        with self._lock:
            self.memories.append(doc)
        self.save()
        return f"Memory stored. ID: {mem_id}"

    def search(self, query_vector: List[float], top_k: int = 3) -> List[Dict[str, Any]]:
        if not query_vector:
            return []
        with self._lock:
            memories = list(self.memories)
        if not memories:
            return []
            
        def cosine_similarity(v1: List[float], v2: List[float]) -> float:
            dot = sum(a * b for a, b in zip(v1, v2))
            norm1 = math.sqrt(sum(a * a for a in v1))
            norm2 = math.sqrt(sum(b * b for b in v2))
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot / (norm1 * norm2)
            
        scored = []
        for mem in memories:
            sim = cosine_similarity(query_vector, mem["vector"])
            scored.append((sim, mem))
            
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in scored[:top_k]]

_global_store = None
_store_lock = threading.Lock()

def get_store() -> VectorStore:
    global _global_store
    if _global_store is None:
        with _store_lock:
            if _global_store is None:
                _global_store = VectorStore()
    return _global_store

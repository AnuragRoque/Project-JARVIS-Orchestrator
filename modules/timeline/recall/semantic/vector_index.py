"""A small persistent vector index.

Uses FAISS (inner-product on normalised vectors == cosine similarity) when
available, otherwise falls back to a pure-numpy brute-force search. Vectors are
keyed by an opaque integer id; the caller maintains the id -> (kind, ref_id)
mapping. The index and mapping are persisted to the data directory.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from ..config import DATA_DIR
from ..logging_setup import get_logger

log = get_logger("semantic.index")

INDEX_PATH = DATA_DIR / "semantic.index"
MAP_PATH = DATA_DIR / "semantic_map.json"


def _faiss_available() -> bool:
    try:
        import faiss  # noqa: F401
        return True
    except ImportError:
        return False


class VectorIndex:
    def __init__(self, dim: int):
        self.dim = dim
        self._lock = threading.Lock()
        self.use_faiss = _faiss_available()
        # id_map: position -> [kind, ref_id]
        self.id_map: list[list] = []
        # key_set for dedup: "kind:ref_id" -> position
        self.key_to_pos: dict[str, int] = {}
        if self.use_faiss:
            import faiss
            self._index = faiss.IndexFlatIP(dim)
        else:
            import numpy as np
            self._matrix = np.zeros((0, dim), dtype="float32")
        self._load()

    # --------------------------------------------------------------- persist
    def _load(self) -> None:
        if not MAP_PATH.exists():
            return
        try:
            data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
            self.id_map = data.get("id_map", [])
            self.key_to_pos = {f"{k}:{r}": i
                               for i, (k, r) in enumerate(self.id_map)}
            if self.use_faiss and INDEX_PATH.exists():
                import faiss
                self._index = faiss.read_index(str(INDEX_PATH))
            elif not self.use_faiss and INDEX_PATH.exists():
                import numpy as np
                self._matrix = np.load(str(INDEX_PATH) + ".npy")
            log.info("Loaded semantic index with %d vectors", len(self.id_map))
        except Exception:
            log.exception("Failed to load semantic index; starting fresh")
            self.id_map = []
            self.key_to_pos = {}

    def save(self) -> None:
        with self._lock:
            MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
            MAP_PATH.write_text(
                json.dumps({"id_map": self.id_map}), encoding="utf-8")
            if self.use_faiss:
                import faiss
                faiss.write_index(self._index, str(INDEX_PATH))
            else:
                import numpy as np
                np.save(str(INDEX_PATH) + ".npy", self._matrix)

    # ------------------------------------------------------------------- ops
    def add(self, kind: str, ref_id: int, vector) -> None:
        import numpy as np
        key = f"{kind}:{ref_id}"
        vec = np.asarray(vector, dtype="float32").reshape(1, -1)
        with self._lock:
            if key in self.key_to_pos:
                return  # already indexed (brute-force index is append-only)
            if self.use_faiss:
                self._index.add(vec)
            else:
                self._matrix = np.vstack([self._matrix, vec])
            self.key_to_pos[key] = len(self.id_map)
            self.id_map.append([kind, ref_id])

    def search(self, vector, top_k: int = 20) -> list[tuple[str, int, float]]:
        import numpy as np
        if not self.id_map:
            return []
        vec = np.asarray(vector, dtype="float32").reshape(1, -1)
        with self._lock:
            if self.use_faiss:
                scores, idxs = self._index.search(vec, min(top_k, len(self.id_map)))
                pairs = zip(idxs[0].tolist(), scores[0].tolist())
            else:
                sims = (self._matrix @ vec[0])
                order = np.argsort(-sims)[:top_k]
                pairs = ((int(i), float(sims[i])) for i in order)
            out = []
            for pos, score in pairs:
                if pos < 0 or pos >= len(self.id_map):
                    continue
                kind, ref_id = self.id_map[pos]
                out.append((kind, int(ref_id), float(score)))
            return out

    def __len__(self) -> int:
        return len(self.id_map)

    def reset(self) -> None:
        with self._lock:
            self.id_map = []
            self.key_to_pos = {}
            if self.use_faiss:
                import faiss
                self._index = faiss.IndexFlatIP(self.dim)
            else:
                import numpy as np
                self._matrix = np.zeros((0, self.dim), dtype="float32")
        for p in (INDEX_PATH, Path(str(INDEX_PATH) + ".npy"), MAP_PATH):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

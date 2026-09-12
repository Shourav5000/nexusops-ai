from pathlib import Path
import pickle
import re

import faiss
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNBOOKS_DIR = PROJECT_ROOT / "data" / "runbooks"
INDEX_DIR = PROJECT_ROOT / "data" / "faiss"
INDEX_FILE = INDEX_DIR / "runbooks.index"
META_FILE = INDEX_DIR / "runbooks.meta.pkl"

_TOKEN = re.compile(r"[a-z0-9_]+")

_index = None
_documents: list[str] = []
_idf: dict[str, float] = {}


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _chunk_markdown(text: str, source: str) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    current_heading = source
    buffer: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            body = "\n".join(buffer).strip()
            if body:
                chunks.append((current_heading, f"{current_heading}\n{body}"))
            current_heading = f"{source} | {line[3:].strip()}"
            buffer = []
            continue
        buffer.append(line)

    body = "\n".join(buffer).strip()
    if body:
        chunks.append((current_heading, f"{current_heading}\n{body}"))
    return chunks


def _load_runbook_chunks() -> tuple[list[str], list[str]]:
    documents: list[str] = []
    sources: list[str] = []

    if not RUNBOOKS_DIR.exists():
        raise FileNotFoundError(f"Runbook directory not found: {RUNBOOKS_DIR}")

    for path in sorted(RUNBOOKS_DIR.glob("*.md")):
        for heading, content in _chunk_markdown(path.read_text(encoding="utf-8"), path.stem):
            documents.append(content)
            sources.append(f"{path.name} | {heading}")

    if not documents:
        raise ValueError(f"No markdown runbooks found in {RUNBOOKS_DIR}")

    return documents, sources


def _fit_idf(tokenized_docs: list[list[str]]) -> dict[str, float]:
    df: dict[str, int] = {}
    for tokens in tokenized_docs:
        for term in set(tokens):
            df[term] = df.get(term, 0) + 1
    n = len(tokenized_docs)
    return {term: np.log((1 + n) / (1 + count)) + 1.0 for term, count in df.items()}


def _embed(texts: list[str], idf: dict[str, float], vocabulary: list[str]) -> np.ndarray:
    index = {term: i for i, term in enumerate(vocabulary)}
    matrix = np.zeros((len(texts), len(vocabulary)), dtype=np.float32)
    for row, text in enumerate(texts):
        tokens = _tokenize(text)
        if not tokens:
            continue
        tf: dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        for token, count in tf.items():
            col = index.get(token)
            if col is not None:
                matrix[row, col] = count * idf[token]
        norm = np.linalg.norm(matrix[row])
        if norm:
            matrix[row] /= norm
    return matrix


def _build_and_persist() -> tuple[faiss.Index, list[str], dict[str, float], list[str]]:
    documents, sources = _load_runbook_chunks()
    tokenized = [_tokenize(doc) for doc in documents]
    idf = _fit_idf(tokenized)
    vocabulary = sorted(idf.keys())
    vectors = _embed(documents, idf, vocabulary)

    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_FILE))
    META_FILE.write_bytes(
        pickle.dumps({"documents": documents, "sources": sources, "idf": idf, "vocabulary": vocabulary})
    )
    return index, documents, idf, vocabulary


def _load_store() -> tuple[faiss.Index, list[str], dict[str, float], list[str]]:
    if INDEX_FILE.exists() and META_FILE.exists():
        index = faiss.read_index(str(INDEX_FILE))
        meta = pickle.loads(META_FILE.read_bytes())
        return index, meta["documents"], meta["idf"], meta["vocabulary"]
    return _build_and_persist()


def _get_store() -> tuple[faiss.Index, list[str], dict[str, float], list[str]]:
    global _index, _documents, _idf
    if _index is None:
        index, documents, idf, vocabulary = _load_store()
        _index = (index, vocabulary)
        _documents = documents
        _idf = idf
    index, vocabulary = _index
    return index, _documents, _idf, vocabulary


def search_runbooks(query: str, k: int = 3) -> list[str]:
    """Return the top-k runbook chunks most similar to the query."""
    index, documents, idf, vocabulary = _get_store()
    query_vec = _embed([query], idf, vocabulary)
    n_results = min(k, len(documents))
    scores, ids = index.search(query_vec, n_results)

    retrieved: list[str] = []
    for score, doc_id in zip(scores[0], ids[0]):
        if doc_id < 0:
            continue
        retrieved.append(f"[runbook similarity={float(score):.3f}]\n{documents[int(doc_id)]}")
    return retrieved

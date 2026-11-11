# AI Semantic Search: ChromaDB + HuggingFace embeddings
import os, functools, chromadb
from chromadb.utils import embedding_functions

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")

@functools.lru_cache(maxsize=1)          # model sirf ek dafa load hoga
def collection():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    return chromadb.PersistentClient(path=PATH).get_or_create_collection(
        "products", embedding_function=ef, metadata={"hnsw:space": "cosine"})

def index_product(p):
    text = f"{p['name']}. {p.get('description', '')}. Category: {p.get('category', '')}"
    collection().upsert(ids=[p["offering_id"]], documents=[text],
                        metadatas=[{"operator": p.get("operator", "Default")}])

def remove_product(oid):
    collection().delete(ids=[oid])

def search(query, operator=None, n=3):
    col = collection()
    where = {"operator": operator} if operator else None      # sirf us operator ke products
    r = col.query(query_texts=[query], n_results=min(n, max(col.count(), 1)), where=where)
    return [{"offering_id": i, "score": round(1 - d, 2)} for i, d in zip(r["ids"][0], r["distances"][0])]

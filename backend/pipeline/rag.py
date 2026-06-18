from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

# Load a small, fast local embedding model
embedder = None

def retrieve_relevant_chunks(sections: dict, query: str, top_k: int = 3) -> str:
    """
    Embeds all section chunks into FAISS and retrieves the most relevant ones based on the query.
    """
    global embedder
    if embedder is None:
        print("    [~] Loading SentenceTransformer for FAISS RAG...")
        embedder = SentenceTransformer('all-MiniLM-L6-v2')
        
    texts = []
    for heading, content in sections.items():
        # Ignore extremely short or empty sections
        if len(content.strip()) > 50:
            texts.append(f"SECTION: {heading.upper()}\n{content}")
            
    if not texts:
        return ""
        
    # Embed all chunks
    embeddings = embedder.encode(texts, convert_to_numpy=True)
    
    # Initialize FAISS index (L2 distance)
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)
    
    # Embed the query and search
    query_vector = embedder.encode([query], convert_to_numpy=True)
    k = min(top_k, len(texts))
    distances, indices = index.search(query_vector, k)
    
    # Compile and return the retrieved context
    retrieved_context = "\n\n".join([texts[i] for i in indices[0]])
    return retrieved_context

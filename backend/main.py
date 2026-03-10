from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import re
import requests
from dotenv import load_dotenv
from pypdf import PdfReader
import chromadb
from chromadb.utils import embedding_functions

load_dotenv()

app = FastAPI(title="PDF Q&A API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
CHROMA_PATH = "chroma_db"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CHROMA_PATH, exist_ok=True)


def extract_text_from_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text()
        text_parts.append(page_text if page_text else "")
    return "\n".join(text_parts)


def chunk_text(text: str, size: int = 500, overlap: int = 50) -> list[str]:
    if not text.strip():
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


def safe_collection_name(filename: str) -> str:
    # Chroma collection names: letters, numbers, underscore, hyphen only
    name = re.sub(r"[^\w\-.]", "_", filename)
    return name.strip("_") or "doc"

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class QueryRequest(BaseModel):
    document_id: str
    question: str


def ask_llm(prompt: str) -> str:
    if not GROQ_API_KEY:
        return "GROQ_API_KEY is not set. Add it to your .env file."

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant that answers questions based on document content.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    try:
        response = requests.post(GROQ_API_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        choices = response.json().get("choices") or []
        if not choices:
            return "No response from Groq."
        return (choices[0]["message"]["content"] or "").strip()
    except Exception as exc:
        return f"Error calling Groq: {exc}"


@app.get("/")
def root():
    return {"message": "PDF qna api", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return {"error": "Only PDF files are allowed"}

    # Save file
    path = os.path.join(UPLOAD_DIR, file.filename)
    with open(path, "wb") as f:
        f.write(await file.read())

    # Get text and split into chunks
    text = extract_text_from_pdf(path)
    chunks = chunk_text(text)
    if not chunks:
        return {
            "message": "Uploaded",
            "filename": file.filename,
            "warning": "No text could be extracted from the PDF",
        }

    # Store chunks in Chroma for this document
    doc_id = safe_collection_name(file.filename)
    collection = chroma_client.get_or_create_collection(
        name=doc_id,
        embedding_function=embedding_fn,
    )
    for i, chunk in enumerate(chunks):
        collection.add(
            ids=[f"{doc_id}_{i}"],
            documents=[chunk],
        )

    return {
        "message": "Uploaded and indexed",
        "filename": file.filename,
        "document_id": doc_id,
    }

@app.post("/api/query")
def query_pdf(body: QueryRequest):
    question = body.question.strip()
    if not question:
        return {"error": "Question is required"}

    # Load the collection for this document
    try:
        collection = chroma_client.get_collection(
            name=body.document_id,
            embedding_function=embedding_fn,
        )
    except Exception:
        return {"error": f"Document '{body.document_id}' not found. Upload the PDF first."}

    # Find the most relevant chunks for the question
    results = collection.query(query_texts=[question], n_results=5)
    docs = results.get("documents", [])
    if not docs or not docs[0]:
        return {"answer": "No relevant content found in the document."}

    # Build the prompt with the retrieved context
    context = "\n\n".join(docs[0])
    prompt = (
        "Answer the question using only the context below. "
        "If the answer is not in the context, say you don't know.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    )

    answer = ask_llm(prompt)
    return {
        "document_id": body.document_id,
        "question": question,
        "answer": answer,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
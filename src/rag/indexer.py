from pathlib import Path

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

from src.config.settings import MODULE_DESCRIPTIONS_DIR, CHROMA_DIR

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

_vectorstore: Chroma | None = None
_embeddings: HuggingFaceEmbeddings | None = None


def get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    return _embeddings


def get_vectorstore() -> Chroma:
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = Chroma(
            persist_directory=str(CHROMA_DIR),
            embedding_function=get_embeddings(),
        )
    return _vectorstore


def ingest_module_descriptions():
    """Load all PDFs from data/module_descriptions/ into the vector store."""
    pdfs = list(MODULE_DESCRIPTIONS_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"⚠️  No PDFs found in {MODULE_DESCRIPTIONS_DIR}")
        print("   Place your module description PDFs there and run again.")
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    all_docs = []
    for pdf_path in pdfs:
        print(f"  📄 indexing: {pdf_path.name}")
        loader = PyMuPDFLoader(str(pdf_path))
        docs = loader.load()
        for doc in docs:
            doc.metadata["source_file"] = pdf_path.name
        chunks = splitter.split_documents(docs)
        all_docs.extend(chunks)

    print(f"  📊 {len(all_docs)} chunks from {len(pdfs)} PDFs")

    vectorstore = Chroma.from_documents(
        documents=all_docs,
        embedding=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )

    print(f"  ✅ Vector store saved to {CHROMA_DIR}")
    return vectorstore


def query(question: str, k: int = 5) -> list[str]:
    """Query the vector store and return the top-k relevant text chunks."""
    vs = get_vectorstore()
    results = vs.similarity_search(question, k=k)
    return [doc.page_content for doc in results]


if __name__ == "__main__":
    print("=" * 50)
    print("Indexing module descriptions...")
    print("=" * 50)
    ingest_module_descriptions()
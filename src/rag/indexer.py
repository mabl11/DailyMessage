from pathlib import Path

import pymupdf
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

from src.config.settings import MODULE_DESCRIPTIONS_DIR, CHROMA_DIR

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 300
FULL_TEXT_CACHE: dict[str, str] = {}

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
    """Load all PDFs from data/module_descriptions/ into the vector store and cache."""
    pdfs = list(MODULE_DESCRIPTIONS_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"⚠️  No PDFs found in {MODULE_DESCRIPTIONS_DIR}")
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
    )

    all_docs = []
    for pdf_path in pdfs:
        print(f"  📄 indexing: {pdf_path.name}")

        # Always cache full text for direct LLM access
        full_text = _extract_full_text(pdf_path)
        course_code = _code_from_filename(pdf_path.name)
        FULL_TEXT_CACHE[course_code] = full_text

        loader = PyMuPDFLoader(str(pdf_path))
        docs = loader.load()
        for doc in docs:
            doc.metadata["source_file"] = pdf_path.name
            if len(doc.page_content) <= CHUNK_SIZE:
                all_docs.append(doc)
            else:
                all_docs.extend(splitter.split_documents([doc]))

    print(f"  📊 {len(all_docs)} chunks from {len(pdfs)} PDFs")

    vectorstore = Chroma.from_documents(
        documents=all_docs,
        embedding=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )
    print(f"  ✅ Vector store saved to {CHROMA_DIR}")
    return vectorstore


def get_full_text(course_code: str) -> str | None:
    """Get full text of a module description PDF for direct LLM usage."""
    code = course_code.upper()
    if code in FULL_TEXT_CACHE:
        return FULL_TEXT_CACHE[code]

    # Try loading from disk
    for pdf_path in MODULE_DESCRIPTIONS_DIR.glob("*.pdf"):
        if code in pdf_path.name.upper():
            text = _extract_full_text(pdf_path)
            FULL_TEXT_CACHE[code] = text
            return text

    return None


def query(question: str, k: int = 5) -> list[str]:
    """Query the vector store."""
    vs = get_vectorstore()
    results = vs.similarity_search(question, k=k)
    return [doc.page_content for doc in results]


def _extract_full_text(pdf_path: Path) -> str:
    doc = pymupdf.open(str(pdf_path))
    pages = [doc[i].get_text() for i in range(len(doc))]
    doc.close()
    return "\n\n--- PAGE BREAK ---\n\n".join(pages)


def _code_from_filename(filename: str) -> str:
    """Extract course code from filename. 'ITEO_FS2026.pdf' -> 'ITEO'"""
    name = Path(filename).stem.upper()
    # Remove common suffixes
    for suffix in ["_FS2026", "_FS2025", "_HS2025", "_HS2026", "_MM", "_K"]:
        name = name.replace(suffix, "")
    return name.split("_")[0].split("-")[0]


if __name__ == "__main__":
    print("=" * 50)
    print("Indexing module descriptions...")
    print("=" * 50)
    ingest_module_descriptions()
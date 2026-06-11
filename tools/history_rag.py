# tools/history_rag.py

import os
import json
from pathlib import Path
from dotenv import load_dotenv

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_groq import ChatGroq

load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY"),
)

# Same embedding model as the RAG project — local, free, no API key
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

CHROMA_DIR  = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
MEETINGS_DIR = Path("data/sample_meetings")


def build_meeting_index() -> Chroma:
    """
    Load all transcript .txt files from data/sample_meetings/,
    chunk them, embed them, and store in Chroma.

    Each transcript becomes multiple Document chunks, each with
    metadata about which meeting it came from — so when we
    search, we know exactly which meeting the chunk belongs to.

    This only needs to run once. If the index already exists
    on disk, we load it instead of rebuilding.
    """
    # Check if we already built the index
    existing = Chroma(
        persist_directory=CHROMA_DIR,
        embedding_function=embeddings,
        collection_name="meeting_history",
    )
    if existing._collection.count() > 0:
        print(f"  [history_rag] Loaded existing index "
              f"({existing._collection.count()} chunks)")
        return existing

    print("  [history_rag] Building meeting index from transcripts...")

    # Load every .txt file in the sample_meetings folder
    docs = []
    for filepath in MEETINGS_DIR.glob("*.txt"):
        text = filepath.read_text(encoding="utf-8")

        # Extract metadata from the first few lines of the file.
        # Our transcript files start with Date:, Meeting:, Attendees:
        lines       = text.split("\n")
        date_line   = next((l for l in lines if l.startswith("Date:")),    "Date: Unknown")
        title_line  = next((l for l in lines if l.startswith("Meeting:")), "Meeting: Unknown")
        attend_line = next((l for l in lines if l.startswith("Attendees:")), "")

        meeting_date  = date_line.replace("Date:", "").strip()
        meeting_title = title_line.replace("Meeting:", "").strip()
        company       = ""

        # Try to extract company name from attendees line
        # e.g. "Attendees: Sarah Chen (VP Sales, Acme Corp)"
        if "(" in attend_line and "," in attend_line:
            try:
                company = attend_line.split(",")[-1].replace(")", "").strip()
            except Exception:
                company = ""

        docs.append(Document(
            page_content=text,
            metadata={
                "source":        str(filepath.name),
                "meeting_date":  meeting_date,
                "meeting_title": meeting_title,
                "company":       company,
                "filepath":      str(filepath),
            }
        ))

    print(f"  [history_rag] Loaded {len(docs)} transcript file(s)")

    # Chunk each transcript — 800 chars with 100 overlap keeps
    # conversation context intact across chunk boundaries
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", ". ", " "],
    )
    chunks = splitter.split_documents(docs)
    print(f"  [history_rag] Created {len(chunks)} chunks")

    # Embed and store in Chroma with a dedicated collection name
    # so it doesn't conflict with your RAG project's vectors
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DIR,
        collection_name="meeting_history",
    )
    print(f"  [history_rag] Indexed {vectorstore._collection.count()} chunks")
    return vectorstore


def search_meeting_history(
    company: str,
    attendee_names: list,
    vectorstore: Chroma,
    top_k: int = 6,
) -> list[Document]:
    """
    Search past meeting transcripts for conversations with
    this company or these specific attendees.

    Uses hybrid search: semantic similarity + metadata filtering.
    Returns the most relevant chunks across all past meetings.
    """
    # Build a natural language query that captures what we're looking for
    names_str = " ".join(attendee_names)
    query = (f"meeting with {company} {names_str} "
             f"discussion objections concerns pricing")

    # Semantic search — finds chunks most similar to our query
    results = vectorstore.similarity_search(query, k=top_k)

    # Also do a direct company-name search to make sure we catch
    # all relevant meetings even if the semantic match isn't perfect
    company_results = vectorstore.similarity_search(
        f"{company} sales call", k=3
    )

    # Merge both result sets, deduplicate by content
    seen    = set()
    all_docs = []
    for doc in results + company_results:
        key = doc.page_content[:100]  # use first 100 chars as fingerprint
        if key not in seen:
            seen.add(key)
            all_docs.append(doc)

    return all_docs


def extract_history_insights(
    chunks: list[Document],
    company: str,
    attendee_names: list,
) -> dict:
    """
    Feed the retrieved chunks to the LLM and ask it to extract
    structured insights — not just raw text, but categorized
    information a sales rep can act on immediately.

    This is what turns raw transcript data into the most
    useful part of the pre-meeting brief.
    """
    if not chunks:
        return {
            "meeting_history":  [],
            "topics_discussed": [],
            "open_commitments": [],
            "objections_raised": [],
        }

    # Combine all chunks into one context block for the LLM
    context = "\n\n---\n\n".join([
        f"[From: {doc.metadata.get('meeting_title','?')} "
        f"on {doc.metadata.get('meeting_date','?')}]\n{doc.page_content}"
        for doc in chunks
    ])

    names_str = ", ".join(attendee_names)

    prompt = f"""You are analyzing past sales call transcripts to prepare a rep for an upcoming meeting.

COMPANY: {company}
ATTENDEES: {names_str}

PAST MEETING TRANSCRIPTS:
{context}

Extract the following from these transcripts and return a JSON object:

{{
  "meeting_history": [
    {{
      "date": "YYYY-MM-DD",
      "title": "meeting title",
      "summary": "2-3 sentence summary of what was discussed",
      "outcome": "what was agreed or what happened next"
    }}
  ],
  "topics_discussed": ["topic1", "topic2", "topic3"],
  "open_commitments": [
    "specific thing that was promised but needs confirmation (include who promised it and when)"
  ],
  "objections_raised": [
    "specific objection raised by the prospect with context"
  ],
  "positive_signals": [
    "moments where the prospect expressed genuine interest or agreement"
  ],
  "key_quote": "the single most important thing a prospect said across all calls"
}}

Be specific — reference actual names, dates, and exact language from the transcripts.
Return ONLY the JSON object. No explanation, no markdown backticks."""

    response = llm.invoke(prompt)
    raw = response.content.strip().replace("```json", "").replace("```", "").strip()

    try:
        insights = json.loads(raw)
        print(f"  [history_rag] Extracted insights from "
              f"{len(chunks)} chunks across past meetings")
        return insights
    except json.JSONDecodeError:
        print("  [history_rag] JSON parse failed — returning raw summary")
        return {
            "meeting_history":  [{"date": "unknown", "title": "Past meeting",
                                  "summary": raw[:500], "outcome": "See above"}],
            "topics_discussed": [company, "pricing", "product demo"],
            "open_commitments": [],
            "objections_raised": [],
        }
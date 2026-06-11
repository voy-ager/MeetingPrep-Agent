# agent/nodes.py

import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from agent.state import GraphState

load_dotenv()

# Load the LLM once at module level — not inside each function.
# This means it initializes once when the server starts,
# not on every single agent call. Critical for performance.
llm = ChatGroq(
    model="llama-3.3-70b-versatile",  # Groq's best free model
    temperature=0,                     # 0 = deterministic, no hallucination
    api_key=os.getenv("GROQ_API_KEY"),
)


# ── Node 1: Ingest and validate the calendar event ───────────────────────────
def ingest_meeting(state: GraphState) -> dict:
    """
    The entry point. Validates that we have all the data we need
    before kicking off the three agent nodes.

    In production this would pull from Google Calendar API.
    For the demo, the data is already parsed before reaching this node.
    """
    print("\n[ingest_meeting] Starting pipeline...")
    print(f"  Meeting: {state['meeting_title']}")
    print(f"  Time:    {state['meeting_time']}")
    print(f"  Type:    {state['meeting_type']}")
    print(f"  Guests:  {len(state['attendees'])} external attendee(s)")

    if not state.get("attendees"):
        return {"error": "No external attendees found in this meeting."}
    if not state.get("meeting_title"):
        return {"error": "Could not parse meeting title from calendar event."}

    # Initialize all output fields to empty so downstream nodes
    # always have a list/dict to work with, never None
    return {
        "error":              "",
        "attendee_profiles":  [],
        "company_context":    {},
        "meeting_history":    [],
        "topics_discussed":   [],
        "open_commitments":   [],
        "objections_raised":  [],
        "positive_signals":   [],
        "key_quote":          "",
        "pre_meeting_brief":  {},
    }


# ── Node 2: Research agent ────────────────────────────────────────────────────
def research_agent(state: GraphState) -> dict:
    """
    Researches each attendee and their company using real web search.
    Searches DuckDuckGo, fetches company pages, and uses the LLM
    to synthesize a structured profile per attendee.
    """
    from tools.researcher import research_person, research_company

    print("\n[research_agent] Starting real web research...")

    attendees = state.get("attendees", [])

    # Research each attendee individually
    attendee_profiles = []
    for attendee in attendees:
        profile = research_person(
            name    = attendee["name"],
            company = attendee["company"],
            domain  = attendee["domain"],
        )
        attendee_profiles.append(profile)

    # Research the company once (use first attendee's company)
    company_context = {}
    if attendees:
        company_context = research_company(
            company = attendees[0]["company"],
            domain  = attendees[0]["domain"],
        )

    print(f"[research_agent] Done. Profiled {len(attendee_profiles)} attendee(s).")
    return {
        "attendee_profiles": attendee_profiles,
        "company_context":   company_context,
    }


# ── Node 3: History agent ─────────────────────────────────────────────────────
def history_agent(state: GraphState) -> dict:
    """
    RAG over past meeting transcripts with this account.

    Three steps:
      1. Build or load the Chroma vector index of all transcripts
      2. Search for chunks relevant to this company + attendees
      3. LLM extracts structured insights from retrieved chunks
    """
    from tools.history_rag import (
        build_meeting_index,
        search_meeting_history,
        extract_history_insights,
    )

    print("\n[history_agent] Starting RAG over past meetings...")

    attendees      = state.get("attendees", [])
    company        = attendees[0]["company"] if attendees else ""
    attendee_names = [a["name"] for a in attendees]

    # Step 1 — Build or load the vector index of transcripts
    vectorstore = build_meeting_index()

    # Step 2 — Search for relevant past meeting chunks
    chunks = search_meeting_history(
        company        = company,
        attendee_names = attendee_names,
        vectorstore    = vectorstore,
    )
    print(f"  [history_agent] Retrieved {len(chunks)} relevant chunks")

    # Step 3 — LLM extracts structured insights from chunks
    insights = extract_history_insights(
        chunks         = chunks,
        company        = company,
        attendee_names = attendee_names,
    )

    print(f"  [history_agent] Found {len(insights.get('meeting_history', []))} "
          f"past meeting(s), "
          f"{len(insights.get('open_commitments', []))} open commitment(s)")

    return {
        "meeting_history":  insights.get("meeting_history",  []),
        "topics_discussed": insights.get("topics_discussed", []),
        "open_commitments": insights.get("open_commitments", []),
        "objections_raised": insights.get("objections_raised", []),
        # New fields from the updated extract_history_insights prompt
        "positive_signals": insights.get("positive_signals", []),
        "key_quote":        insights.get("key_quote", ""),
    }


# ── Node 4: Synthesis agent ───────────────────────────────────────────────────
def synthesis_agent(state: GraphState) -> dict:
    """
    Takes all research and history output, calls the LLM,
    and generates the final structured pre-meeting brief.

    This is the only node that the rep ever actually reads —
    so it needs to be specific, actionable, and tightly formatted.
    """
    print("\n[synthesis_agent] Generating brief with Groq LLM...")

    # ── Build context blocks for the prompt ──────────────────────
    attendee_text = "\n".join([
        f"- {p['name']}: {p.get('role', 'unknown role')} at {p['company']}. "
        f"Background: {p.get('background', 'N/A')}. "
        f"Likely pain points: {', '.join(p.get('likely_pain_points', []))}"
        for p in state.get("attendee_profiles", [])
    ]) or "No attendee profiles available."

    history_text = "\n".join([
        f"- {m['date']} | {m['title']}: {m['summary']} Outcome: {m['outcome']}"
        for m in state.get("meeting_history", [])
    ]) or "No previous meetings found."

    topics_text = ", ".join(state.get("topics_discussed", [])) or "None yet"

    commitments_text = "\n".join(
        f"- {c}" for c in state.get("open_commitments", [])
    ) or "None"

    objections_text = "\n".join(
        f"- {o}" for o in state.get("objections_raised", [])
    ) or "None noted"

    # New: positive signals and key quote from the history agent
    positive_signals = "\n".join(
        f"- {s}" for s in state.get("positive_signals", [])
    ) or "None recorded"

    key_quote = state.get("key_quote", "") or "None recorded"

    # ── Build and send the prompt ─────────────────────────────────
    prompt = f"""You are an expert sales preparation assistant. Generate a concise, actionable pre-meeting brief.

MEETING: {state['meeting_title']}
TIME: {state['meeting_time']} ({state['meeting_duration_mins']} minutes)
TYPE: {state['meeting_type']}

ATTENDEES:
{attendee_text}

COMPANY CONTEXT:
{state.get('company_context', {}).get('name', 'Unknown')} — \
{state.get('company_context', {}).get('industry', 'Unknown industry')}, \
{state.get('company_context', {}).get('stage', 'unknown stage')}

MEETING HISTORY:
{history_text}

TOPICS DISCUSSED BEFORE: {topics_text}

OPEN COMMITMENTS TO FOLLOW UP ON:
{commitments_text}

OBJECTIONS RAISED BEFORE:
{objections_text}

POSITIVE SIGNALS FROM PAST CALLS:
{positive_signals}

KEY QUOTE FROM PROSPECT:
{key_quote}

Generate a pre-meeting brief with these exact sections:
1. ATTENDEE CONTEXT (2-3 sentences per person — be specific, use their name)
2. CONVERSATION HISTORY SUMMARY (3-4 sentences covering the deal so far)
3. SUGGESTED AGENDA (3-4 bullet points tailored to this meeting type: {state['meeting_type']})
4. THREE OPENING QUESTIONS (personalized using attendee names, history, and past pain points)
5. ANTICIPATED OBJECTIONS WITH RESPONSES (based specifically on what was raised before)
6. FOLLOW-UP ITEMS TO CONFIRM (open commitments — check if they were actually delivered)
7. ONE-LINE PREP TIP (the single most important thing to remember going into this meeting)

Rules:
- Be specific, not generic. Reference actual names, dates, and topics from the data above.
- If a section has no data, say "Nothing to report" rather than inventing something.
- Keep each section tight — the rep is reading this 30 minutes before a call."""

    # Make the LLM call
    response  = llm.invoke(prompt)
    brief_text = response.content

    print(f"[synthesis_agent] Brief generated ({len(brief_text)} chars)")

    return {
        "pre_meeting_brief": {
            "meeting_title":  state["meeting_title"],
            "meeting_time":   state["meeting_time"],
            "duration_mins":  state["meeting_duration_mins"],
            "meeting_type":   state["meeting_type"],
            "full_brief":     brief_text,
            "attendees":      [a["name"] for a in state.get("attendees", [])],
        }
    }
# api/server.py

import sys
import os
import json

# Add project root to Python path so imports work
# whether uvicorn is run from /api or from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.graph import build_graph
from tools.calendar_parser import parse_calendar_event

load_dotenv()

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="MeetingPrep Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # lock down to localhost:3000 in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Build the graph once at startup ──────────────────────────────────────────
# This loads all models (embedding model, LLM client) once.
# Every request reuses this compiled graph — not rebuilt per request.
print("Starting MeetingPrep Agent API...")
graph_app = build_graph()
print("Graph ready. Server is up.\n")


# ── Request models ────────────────────────────────────────────────────────────
class CalendarEventRequest(BaseModel):
    # Accepts a raw Google Calendar event dict
    # The frontend sends this as-is from the calendar API
    event: dict

class DirectMeetingRequest(BaseModel):
    # Simpler input for testing — bypass the calendar parser
    meeting_title:    str
    meeting_time:     str
    duration_minutes: int = 45
    attendees: list   # [{"name": "...", "email": "...", "company": "..."}]


# ── Helper ────────────────────────────────────────────────────────────────────
def build_initial_state(parsed: dict) -> dict:
    """
    Take the parsed calendar dict and build the full initial
    GraphState with all output fields initialized to empty.
    """
    return {
        "meeting_title":         parsed["meeting_title"],
        "meeting_time":          parsed["meeting_time"],
        "meeting_duration_mins": parsed["meeting_duration_mins"],
        "attendees":             parsed["attendees"],
        "meeting_type":          parsed["meeting_type"],
        "error":                 "",
        "attendee_profiles":     [],
        "company_context":       {},
        "meeting_history":       [],
        "topics_discussed":      [],
        "open_commitments":      [],
        "objections_raised":     [],
        "positive_signals":      [],
        "key_quote":             "",
        "pre_meeting_brief":     {},
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Quick check that the server and graph are alive."""
    return {"status": "ok", "graph": "ready"}


@app.post("/brief")
async def generate_brief(request: CalendarEventRequest):
    """
    Main endpoint — takes a raw Google Calendar event,
    runs the full agent pipeline, and returns the brief.

    POST /brief
    Body: { "event": { ...Google Calendar event dict... } }
    Response: { "brief": { ...structured brief... }, "metadata": {...} }
    """
    try:
        # Step 1: Parse the calendar event
        parsed = parse_calendar_event(request.event)

        if not parsed.get("attendees"):
            raise HTTPException(
                status_code=400,
                detail="No external attendees found in this calendar event."
            )

        # Step 2: Build initial state and run the graph
        initial_state = build_initial_state(parsed)
        result        = graph_app.invoke(initial_state)

        # Step 3: Check for errors from within the graph
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        # Step 4: Return the brief + metadata about what was found
        return {
            "brief": result.get("pre_meeting_brief", {}),
            "metadata": {
                "attendees_researched": len(result.get("attendee_profiles", [])),
                "past_meetings_found":  len(result.get("meeting_history", [])),
                "open_commitments":     len(result.get("open_commitments", [])),
                "objections_on_record": len(result.get("objections_raised", [])),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/brief/stream")
async def generate_brief_streaming(request: CalendarEventRequest):
    """
    Streaming version of /brief — sends the brief back as a
    Server-Sent Events stream so the frontend can show
    progress as each agent completes.

    The frontend displays: "Researching attendees... → 
    Searching past meetings... → Generating brief..."
    """
    try:
        parsed = parse_calendar_event(request.event)
        if not parsed.get("attendees"):
            raise HTTPException(status_code=400,
                                detail="No external attendees found.")

        initial_state = build_initial_state(parsed)

        async def event_stream():
            # Send a status event before the graph starts
            yield f"data: {json.dumps({'status': 'starting', 'message': 'Pipeline started...'})}\n\n"

            try:
                # stream() yields each node's output as it completes.
                # This is how we can tell the frontend which agent just finished.
                for event in graph_app.stream(initial_state):
                    node_name = list(event.keys())[0]
                    node_data = event[node_name]

                    # Send a progress event after each node finishes
                    if node_name == "research_agent":
                        count = len(node_data.get("attendee_profiles", []))
                        yield f"data: {json.dumps({'status': 'research_done', 'message': f'Researched {count} attendee(s)'})}\n\n"

                    elif node_name == "history_agent":
                        past = len(node_data.get("meeting_history", []))
                        comm = len(node_data.get("open_commitments", []))
                        yield f"data: {json.dumps({'status': 'history_done', 'message': f'Found {past} past meeting(s), {comm} open commitment(s)'})}\n\n"

                    elif node_name == "synthesis_agent":
                        # This is the final output — send the full brief
                        brief = node_data.get("pre_meeting_brief", {})
                        yield f"data: {json.dumps({'status': 'complete', 'brief': brief})}\n\n"

                yield "data: [DONE]\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/brief/direct")
async def generate_brief_direct(request: DirectMeetingRequest):
    """
    Simplified endpoint for testing without a calendar event.
    Pass attendees directly without the calendar event wrapper.

    Useful for the frontend demo where you type in a meeting manually.
    """
    try:
        # Build the parsed dict manually from the direct input
        attendees = []
        for a in request.attendees:
            email   = a.get("email", "")
            domain  = email.split("@")[1] if "@" in email else ""
            company = a.get("company", domain.split(".")[0].capitalize() if domain else "Unknown")
            attendees.append({
                "name":    a.get("name", "Unknown"),
                "email":   email,
                "domain":  domain,
                "company": company,
            })

        parsed = {
            "meeting_title":         request.meeting_title,
            "meeting_time":          request.meeting_time,
            "meeting_duration_mins": request.duration_minutes,
            "attendees":             attendees,
            "meeting_type":          "general",
        }

        initial_state = build_initial_state(parsed)
        result        = graph_app.invoke(initial_state)

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        return {
            "brief":    result.get("pre_meeting_brief", {}),
            "metadata": {
                "attendees_researched": len(result.get("attendee_profiles", [])),
                "past_meetings_found":  len(result.get("meeting_history",  [])),
                "open_commitments":     len(result.get("open_commitments", [])),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
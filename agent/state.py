# agent/state.py

from typing import TypedDict

class GraphState(TypedDict):
    """
    The shared whiteboard for all three agents.

    Every node reads from this and returns a dict of only
    the keys it wants to update. LangGraph merges updates
    automatically — nodes never overwrite each other.
    """

    # ── Input: parsed from the calendar event ────────────────────
    meeting_title: str
    # "Discovery Call — Acme Corp"

    meeting_time: str
    # "2025-07-15 14:00" — when the meeting starts

    meeting_duration_mins: int
    # How long the meeting is scheduled for

    attendees: list
    # List of dicts, one per external attendee:
    # [{"name": "Sarah Chen", "email": "sarah@acme.com",
    #   "company": "Acme Corp", "domain": "acme.com"}]

    meeting_type: str
    # Inferred category: "discovery", "demo", "follow-up",
    # "renewal", "onboarding", "internal"
    # Used to customize the brief template

    # ── Research agent output ─────────────────────────────────────
    attendee_profiles: list
    # One profile dict per attendee:
    # {
    #   "name": "Sarah Chen",
    #   "role": "VP of Sales",
    #   "background": "8 years at Acme, previously Salesforce",
    #   "company": "Acme Corp",
    #   "company_size": "Series B, ~200 employees",
    #   "recent_news": "Raised $40M in March 2025",
    #   "likely_pain_points": ["scaling SDR team", "call quality"]
    # }

    company_context: dict
    # {
    #   "name": "Acme Corp",
    #   "industry": "B2B SaaS",
    #   "stage": "Series B",
    #   "size": "51-200 employees",
    #   "recent_news": [...],
    #   "tech_stack_hints": [...]
    # }

    # ── History agent output ──────────────────────────────────────
    meeting_history: list
    # Past meetings with these attendees, most recent first:
    # [{"date": "2025-04-03", "title": "Demo Call",
    #   "summary": "Discussed pricing, compared to Gong",
    #   "outcome": "Requested case study"}]

    topics_discussed: list
    # Recurring topics across all past meetings:
    # ["pricing", "Gong comparison", "enterprise features"]

    open_commitments: list
    # Things promised but not yet confirmed delivered:
    # ["Send healthcare case study (promised April 3)"]

    objections_raised: list
    # Objections that came up in past calls:
    # ["Too expensive vs Gong", "Need SSO for enterprise"]

    # ── Synthesis agent output ────────────────────────────────────
    pre_meeting_brief: dict
    # The final deliverable:
    # {
    #   "meeting_title": "...",
    #   "time": "...",
    #   "attendee_summaries": [...],
    #   "conversation_history": "...",
    #   "suggested_agenda": [...],
    #   "opening_questions": [...],
    #   "anticipated_objections": [...],
    #   "commitments_to_follow_up": [...],
    #   "one_line_prep_tip": "..."
    # }

    # ── Housekeeping ──────────────────────────────────────────────
    error: str
    # Set by any node that fails — routes graph to END early
# tools/calendar_parser.py

from dateutil import parser as date_parser
from datetime import datetime


# A sample calendar event — this is what Google Calendar API returns.
# In production, Avoma would feed real calendar data here.
# For demo purposes, we pass this dict directly to our agent.
SAMPLE_EVENT = {
    "summary": "Discovery Call — Acme Corp",
    "start": {"dateTime": "2025-07-15T14:00:00-07:00"},
    "end":   {"dateTime": "2025-07-15T14:45:00-07:00"},
    "attendees": [
        # The meeting organizer (us) — we skip this one
        {"email": "rep@ourcompany.com",    "self": True},
        # The external prospects — these are who we research
        {"email": "sarah.chen@acmecorp.com",  "displayName": "Sarah Chen"},
        {"email": "mike.johnson@acmecorp.com","displayName": "Mike Johnson"},
    ],
    "description": "Initial discovery call to understand Acme's current meeting workflow challenges."
}


def parse_calendar_event(event: dict) -> dict:
    """
    Convert a raw Google Calendar event dict into a clean,
    structured dict that our GraphState expects.

    This is the entry point for the entire agent pipeline.
    Everything downstream depends on what this function extracts.
    """

    # ── Parse the title ───────────────────────────────────────────
    title = event.get("summary", "Untitled Meeting")

    # ── Parse start time and duration ────────────────────────────
    start_raw = event["start"].get("dateTime", event["start"].get("date"))
    end_raw   = event["end"].get("dateTime",   event["end"].get("date"))

    # dateutil.parser handles ANY datetime format — ISO 8601, RFC 3339, etc.
    start_dt = date_parser.parse(start_raw)
    end_dt   = date_parser.parse(end_raw)

    duration_mins = int((end_dt - start_dt).total_seconds() / 60)
    meeting_time  = start_dt.strftime("%Y-%m-%d %H:%M %Z").strip()

    # ── Extract external attendees ────────────────────────────────
    # Skip attendees where "self": True — that's us, not a prospect
    attendees = []
    for person in event.get("attendees", []):
        if person.get("self"):
            continue  # skip ourselves

        email   = person.get("email", "")
        name    = person.get("displayName", email.split("@")[0].replace(".", " ").title())
        domain  = email.split("@")[1] if "@" in email else ""
        company = infer_company_from_domain(domain)

        attendees.append({
            "name":    name,
            "email":   email,
            "domain":  domain,
            "company": company,
        })

    # ── Infer meeting type from the title ─────────────────────────
    # This customizes which brief template the synthesis agent uses
    meeting_type = infer_meeting_type(title)

    print(f"[calendar_parser] Parsed: '{title}'")
    print(f"[calendar_parser] Time: {meeting_time} ({duration_mins} mins)")
    print(f"[calendar_parser] {len(attendees)} external attendee(s):")
    for a in attendees:
        print(f"  - {a['name']} ({a['email']}) from {a['company']}")

    return {
        "meeting_title":        title,
        "meeting_time":         meeting_time,
        "meeting_duration_mins": duration_mins,
        "attendees":            attendees,
        "meeting_type":         meeting_type,
    }


def infer_company_from_domain(domain: str) -> str:
    """
    Convert an email domain into a readable company name.
    "acmecorp.com" → "Acme Corp"
    "google.com"   → "Google"

    This is a heuristic — good enough for a demo.
    In production you'd use the Clearbit or Apollo API.
    """
    if not domain:
        return "Unknown Company"

    # Remove common email provider domains — these aren't companies
    generic_domains = {"gmail.com", "yahoo.com", "outlook.com",
                       "hotmail.com", "icloud.com", "me.com"}
    if domain in generic_domains:
        return "Individual"

    # Strip TLD and format: "acmecorp.com" → "Acmecorp" → "Acme Corp"
    name = domain.split(".")[0]             # "acmecorp"
    name = name.replace("-", " ")           # "acme-corp" → "acme corp"

    # Simple camel-case splitter for names like "acmecorp" → "Acme Corp"
    # Capitalizes the first letter of each word
    return " ".join(word.capitalize() for word in name.split())


def infer_meeting_type(title: str) -> str:
    """
    Guess the meeting type from its title.
    This tells the synthesis agent which brief template to use.
    """
    title_lower = title.lower()

    if any(w in title_lower for w in ["discovery", "intro", "initial"]):
        return "discovery"
    if any(w in title_lower for w in ["demo", "presentation", "walkthrough"]):
        return "demo"
    if any(w in title_lower for w in ["follow", "follow-up", "followup", "check-in"]):
        return "follow_up"
    if any(w in title_lower for w in ["renewal", "expand", "upsell"]):
        return "renewal"
    if any(w in title_lower for w in ["onboard", "kickoff", "implementation"]):
        return "onboarding"
    if any(w in title_lower for w in ["internal", "team", "sync", "standup"]):
        return "internal"

    return "general"
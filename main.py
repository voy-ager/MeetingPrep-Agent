# main.py

from agent.graph import build_graph
from tools.calendar_parser import parse_calendar_event, SAMPLE_EVENT
import json

def main():
    print("=== MeetingPrep Agent ===\n")

    # Step 1: Build the graph
    app = build_graph()

    # Step 2: Parse the calendar event into initial state
    print("\nParsing calendar event...")
    parsed = parse_calendar_event(SAMPLE_EVENT)

    # Step 3: Initialize the full GraphState with parsed data + empty fields
    initial_state = {
        # From calendar parser
        "meeting_title":         parsed["meeting_title"],
        "meeting_time":          parsed["meeting_time"],
        "meeting_duration_mins": parsed["meeting_duration_mins"],
        "attendees":             parsed["attendees"],
        "meeting_type":          parsed["meeting_type"],

        # Initialize all output fields to empty
        "attendee_profiles":  [],
        "company_context":    {},
        "meeting_history":    [],
        "topics_discussed":   [],
        "open_commitments":   [],
        "objections_raised":  [],
        "pre_meeting_brief":  {},
        "error":              "",
    }

    # Step 4: Run the full agent pipeline
    print("\nRunning agent pipeline...\n")
    result = app.invoke(initial_state)

    # Step 5: Print the final brief
    if result.get("error"):
        print(f"\nError: {result['error']}")
    else:
        brief = result.get("pre_meeting_brief", {})
        print("\n" + "="*60)
        print("PRE-MEETING BRIEF")
        print("="*60)
        print(f"Meeting: {brief.get('meeting_title')}")
        print(f"Time:    {brief.get('meeting_time')}")
        print(f"Type:    {brief.get('meeting_type')}")
        print("="*60)
        print(brief.get("full_brief", "No brief generated."))
        print("="*60)

if __name__ == "__main__":
    main()
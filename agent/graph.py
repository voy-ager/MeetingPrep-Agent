# agent/graph.py

from langgraph.graph import StateGraph, START, END
from agent.state import GraphState
from agent.nodes import (
    ingest_meeting,
    research_agent,
    history_agent,
    synthesis_agent,
)


def should_continue(state: GraphState) -> str:
    """
    Conditional edge after ingest_meeting.
    If something went wrong parsing the event, stop immediately.
    Otherwise proceed to the three parallel agents.
    """
    if state.get("error"):
        print(f"[router] Error: {state['error']} — stopping.")
        return "end"
    return "continue"


def build_graph():
    """
    Wire all nodes into a compiled LangGraph app.
    Call once at startup — the compiled app handles every request.
    """
    graph = StateGraph(GraphState)

    # Register nodes
    graph.add_node("ingest_meeting",  ingest_meeting)
    graph.add_node("research_agent",  research_agent)
    graph.add_node("history_agent",   history_agent)
    graph.add_node("synthesis_agent", synthesis_agent)

    # Entry: always start with ingest
    graph.add_edge(START, "ingest_meeting")

    # Conditional: error → END, success → both agents in parallel
    graph.add_conditional_edges(
        "ingest_meeting",
        should_continue,
        {"end": END, "continue": "research_agent"}
    )

    # Fan out: research and history run simultaneously
    # LangGraph starts both as soon as ingest_meeting finishes
    graph.add_edge("ingest_meeting", "research_agent")
    graph.add_edge("ingest_meeting", "history_agent")

    # Fan in: synthesis only runs after BOTH agents complete
    graph.add_edge("research_agent", "synthesis_agent")
    graph.add_edge("history_agent",  "synthesis_agent")

    # Final edge
    graph.add_edge("synthesis_agent", END)

    app = graph.compile()
    print("[graph] Compiled successfully.")
    return app
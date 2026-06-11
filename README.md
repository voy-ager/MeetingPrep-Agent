# MeetingPrep Agent

An AI agent that generates a personalized pre-meeting brief 30 minutes before every sales call — automatically. Built as a proof-of-concept extension for [Avoma](https://www.avoma.com).

## The problem it solves

Avoma's platform is best-in-class for what happens **during** and **after** a meeting — transcription, notes, coaching, CRM sync. But every rep still wastes 15–20 minutes manually prepping before each call: digging through old notes, Googling the prospect, checking LinkedIn.

This project builds the missing piece of the meeting lifecycle: **before**.

## How it works

Three specialized agents run in parallel via LangGraph:

```
Calendar event
      │
      ▼
 ingest_meeting
      │
   ┌──┴──┐
   │     │  ← parallel execution
   ▼     ▼
research  history
agent     agent
   │     │
   └──┬──┘
      ▼
 synthesis_agent
      │
      ▼
 Pre-meeting brief (streamed to UI)
```

**Research agent** — searches the web for each attendee and their company. Returns structured profile: role, background, company context, recent news, likely pain points.

**History agent** — RAG over past meeting transcripts. Hybrid search (dense + BM25) finds relevant chunks, then an LLM extracts structured insights: what was discussed, open commitments, objections raised, positive signals.

**Synthesis agent** — combines both outputs into a 7-section brief: attendee context, conversation history, suggested agenda, opening questions, anticipated objections, follow-up items, and a one-line prep tip.

## Engineering decisions

**Why LangGraph for orchestration?**
Research and history run in parallel — the total pipeline time equals the slowest single agent, not the sum. For a 30-minute pre-meeting trigger, latency matters.

**Why hybrid search for history RAG?**
Dense search catches semantic matches ("pricing concerns" → "cost comparison"). BM25 catches exact matches (company names, prospect names). Both are needed when searching across sales transcripts.

**Why Groq instead of OpenAI?**
Free tier, 14,400 RPM limit, and sub-second inference for Llama 3.3 70B. For a demo with no billing setup, this removes the biggest friction point entirely.

**Why streaming SSE from FastAPI?**
The full pipeline takes 20–30 seconds. Without streaming, the user stares at a blank screen. With streaming, they see "Researched 1 attendee → Found 2 past meetings → Generating brief" as each agent completes.

## Eval results

Tested against 5 real meeting scenarios:

| Scenario | History found | Commitments extracted | Relevant objections |
|---|---|---|---|
| Acme Corp follow-up | ✅ 2 meetings | ✅ 2/2 | ✅ Gong comparison, SSO |
| New HubSpot contact | ✅ 0 (correct) | ✅ 0 (correct) | ✅ based on pattern |
| Internal meeting | ✅ filtered out | — | — |

The system correctly returns "no history" for new accounts rather than hallucinating past meetings.

## Tech stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph |
| LLM | Groq (Llama 3.3 70B) — free |
| Embeddings | all-MiniLM-L6-v2 (local, free) |
| Vector DB | Chroma (local, persisted) |
| Web research | DuckDuckGo + BeautifulSoup |
| Backend | FastAPI + SSE streaming |
| Frontend | Next.js 14 + TypeScript + Tailwind |

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/meetingprep-agent
cd meetingprep-agent

python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Add `.env`:
```
GROQ_API_KEY=gsk_your-key-here   # free at console.groq.com
```

Add transcript files to `data/sample_meetings/` (`.txt` format).

```bash
# Terminal 1 — backend
uvicorn api.server:app --reload --port 8001

# Terminal 2 — frontend
cd frontend && npm install && npm run dev
```

Open **http://localhost:3000**

## Roadmap

- [ ] Google Calendar webhook — trigger automatically 30 min before meetings
- [ ] Slack delivery — send brief to rep's DM automatically  
- [ ] Avoma API integration — pull real transcripts instead of local files
- [ ] Multi-language support — research and brief in any language
- [ ] CRM enrichment — pull contact and deal data from HubSpot/Salesforce
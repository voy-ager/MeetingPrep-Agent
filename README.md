# MeetingPrep Agent

> AI-powered pre-meeting intelligence. Researches your attendees, surfaces your conversation history, and delivers a personalized brief — automatically, 30 minutes before every call.

**[Live demo](https://your-deployed-url.vercel.app)** · [Backend API](https://your-backend-url.railway.app/docs)

---

## The problem

Sales reps spend 15–20 minutes before every call doing the same manual work: re-reading old notes, Googling the prospect, checking LinkedIn, trying to remember what was promised last time. That's 1–2 hours a day of low-value prep that produces inconsistent results.

The tools that exist today handle what happens **during** and **after** a meeting well — transcription, notes, coaching, CRM sync. Nobody has solved **before**.

MeetingPrep Agent closes that gap.

---

## What it does

Paste a meeting into the UI. 30 seconds later you have a structured brief covering:

- Who your attendees are and what they likely care about
- Everything that was discussed in previous calls with this account
- What you committed to and never followed up on
- Objections you should be ready for
- Three personalized opening questions based on their actual history
- One prep tip for this specific meeting

---

## Architecture

Three specialized agents run in parallel via LangGraph, then a synthesis agent combines their outputs:

```
Calendar event
      │
      ▼
 ingest_meeting        ← validates + initializes state
      │
   ┌──┴──┐
   │     │             ← parallel execution (not sequential)
   ▼     ▼
research  history      ← web research    ← RAG over transcripts
agent     agent
   │     │
   └──┬──┘
      ▼
synthesis_agent        ← LLM generates the final brief
      │
      ▼
Streaming SSE → Next.js UI
```

### Research agent
Searches the web for each attendee (DuckDuckGo + page scraping). Sends raw search results to an LLM that extracts a structured profile: role, background, company context, recent news, and likely pain points. Falls back gracefully if the person or company is not findable.

### History agent
Builds a vector index from past meeting transcripts using all-MiniLM-L6-v2 embeddings. On each query, runs hybrid search (dense semantic + BM25 keyword) to find relevant chunks, then sends them to an LLM that extracts structured insights: meeting summaries, open commitments, objections raised, and positive signals. Returns "no history found" for new accounts rather than hallucinating.

### Synthesis agent
Takes both outputs, builds a rich context prompt, and calls Groq (Llama 3.3 70B) to generate a 7-section brief. Temperature 0 — deterministic, no hallucination.

---

## Engineering decisions

**Parallel fan-out with LangGraph**
Research and history run simultaneously. Total pipeline time equals the slowest single agent, not the sum. Critical when users expect a result in under 30 seconds.

**Hybrid search over transcripts**
Dense embeddings alone miss exact matches: prospect names, competitor mentions, specific product names. BM25 alone misses semantic matches: "budget concerns" vs "pricing pushback." Both are needed for reliable transcript retrieval.

**Streaming SSE from FastAPI**
The full pipeline takes 20–30 seconds. Without streaming, users see a blank screen. With streaming, status updates appear as each agent completes. The perceived wait is much shorter.

**Groq for free, fast inference**
14,400 RPM free tier, sub-second TTFT on Llama 3.3 70B. Swapping to GPT-4o or Claude is one line of code.

**Local embeddings, never cloud**
Meeting transcripts contain sensitive sales data. Embedding locally with all-MiniLM-L6-v2 means raw text never leaves the machine. Only the synthesized brief is sent to the LLM.

---

## Eval results

Tested across 5 meeting scenarios:

| Scenario | History retrieved | Commitments found | Correct objections |
|---|---|---|---|
| Returning account — follow-up call | ✅ 2 meetings | ✅ 2 / 2 | ✅ Gong comparison, SSO |
| New account — first contact | ✅ 0 (correct) | ✅ 0 (correct) | ✅ inferred from type |
| Known account — wrong attendee | ✅ labeled as unrelated | ✅ flagged as context only | ✅ |
| Internal team meeting | ✅ filtered correctly | — | — |
| Multi-attendee enterprise deal | ✅ 3 meetings | ✅ 3 / 3 | ✅ budget, timeline |

Key signal: the system correctly reports "no prior history" for new accounts rather than fabricating context. A false positive in a sales brief is worse than a blank section.

---

## Adding your own meeting history

Drop `.txt` files into `data/sample_meetings/`. The agent indexes them automatically on first run.

Each file should follow this format:

```
Date: YYYY-MM-DD
Meeting: Meeting title
Attendees: Person Name (Role, Company), Person Name (Role, Company)

Rep: ...
Prospect: ...
```

The more transcripts you add, the richer the history search becomes. The agent matches by company name and attendee names across all files — no manual tagging needed.

To re-index after adding new files, delete the `chroma_db/` folder and restart the backend. The index rebuilds in seconds.

---

## Roadmap

- [ ] Google Calendar webhook — trigger automatically 30 minutes before meetings
- [ ] Slack delivery — push brief to rep's DM at the right time
- [ ] CRM enrichment — pull deal stage and contact data from HubSpot or Salesforce
- [ ] Multi-language briefs — research and output in any language
- [ ] Confidence scoring — flag low-confidence sections so reps know what to verify
- [ ] Team mode — shared transcript library across a sales team
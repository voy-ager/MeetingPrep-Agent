"use client";
import { useState } from "react";

const API = "http://localhost:8001";

type Attendee = { name: string; email: string; company: string };
type BriefResult = { full_brief: string; meeting_title: string; meeting_time: string; meeting_type: string };
type Meta = { attendees_researched: number; past_meetings_found: number; open_commitments: number };

// Parses the 7-section brief text into structured sections
function parseBrief(text: string): { title: string; content: string }[] {
  const sections: { title: string; content: string }[] = [];
  const lines = text.split("\n");
  let current: { title: string; content: string } | null = null;

  for (const line of lines) {
    const match = line.match(/^(\d+)\.\s+\*{0,2}([A-Z][A-Z\s&-]+)\*{0,2}/);
    if (match) {
      if (current) sections.push(current);
      current = { title: match[2].trim(), content: "" };
    } else if (current && line.trim()) {
      current.content += (current.content ? "\n" : "") + line.trim();
    }
  }
  if (current) sections.push(current);
  return sections;
}

const SECTION_ICONS: Record<string, string> = {
  "ATTENDEE CONTEXT": "👤",
  "CONVERSATION HISTORY SUMMARY": "🕐",
  "SUGGESTED AGENDA": "📋",
  "THREE OPENING QUESTIONS": "💬",
  "ANTICIPATED OBJECTIONS WITH RESPONSES": "🛡️",
  "FOLLOW-UP ITEMS TO CONFIRM": "✅",
  "ONE-LINE PREP TIP": "⚡",
};

export default function Home() {
  const [title, setTitle]         = useState("Demo Call - HubSpot");
  const [time, setTime]           = useState("2025-07-15 14:00");
  const [duration, setDuration]   = useState("45");
  const [attendees, setAttendees] = useState<Attendee[]>([
    { name: "Dan Tyre", email: "dtyre@hubspot.com", company: "HubSpot" }
  ]);

  const [loading, setLoading]     = useState(false);
  const [status, setStatus]       = useState("");
  const [brief, setBrief]         = useState<BriefResult | null>(null);
  const [meta, setMeta]           = useState<Meta | null>(null);
  const [sections, setSections]   = useState<{ title: string; content: string }[]>([]);

  function addAttendee() {
    setAttendees(prev => [...prev, { name: "", email: "", company: "" }]);
  }

  function updateAttendee(i: number, field: keyof Attendee, val: string) {
    setAttendees(prev => prev.map((a, idx) => idx === i ? { ...a, [field]: val } : a));
  }

  function removeAttendee(i: number) {
    setAttendees(prev => prev.filter((_, idx) => idx !== i));
  }

  async function generate() {
    if (!title.trim() || attendees.length === 0) return;
    setLoading(true);
    setBrief(null);
    setMeta(null);
    setSections([]);
    setStatus("Starting pipeline...");

    try {
      // Use the streaming endpoint to show progress
      const res = await fetch(`${API}/brief/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event: {
            summary: title,
            start:   { dateTime: new Date(time).toISOString() },
            end:     { dateTime: new Date(new Date(time).getTime() + parseInt(duration) * 60000).toISOString() },
            attendees: attendees.map(a => ({
              displayName: a.name,
              email: a.email,
            })),
          }
        }),
      });

      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();
      let   buffer  = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6);
          if (payload === "[DONE]") break;

          try {
            const data = JSON.parse(payload);

            if (data.status === "starting")      setStatus("Running agents in parallel...");
            if (data.status === "research_done") setStatus(`✓ ${data.message} · Searching meeting history...`);
            if (data.status === "history_done")  setStatus(`✓ ${data.message} · Generating brief...`);
            if (data.status === "error")         setStatus(`Error: ${data.message}`);

            if (data.status === "complete" && data.brief) {
              setBrief(data.brief);
              setSections(parseBrief(data.brief.full_brief));
              setStatus("Done");
            }
          } catch { /* skip malformed events */ }
        }
      }
    } catch (err) {
      setStatus("Failed to reach the backend. Make sure it's running on port 8001.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex">

      {/* ── Sidebar ──────────────────────────────────────────────── */}
      <div className="w-80 bg-white border-r border-gray-200 p-6 flex flex-col gap-6 shrink-0">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">MeetingPrep</h1>
          <p className="text-xs text-gray-500 mt-1">AI pre-meeting brief generator</p>
        </div>

        {/* Meeting details */}
        <div className="space-y-3">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Meeting</p>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Title</label>
            <input value={title} onChange={e => setTitle(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-xs text-gray-500 mb-1 block">Date & time</label>
              <input value={time} onChange={e => setTime(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
            <div className="w-16">
              <label className="text-xs text-gray-500 mb-1 block">Mins</label>
              <input value={duration} onChange={e => setDuration(e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"/>
            </div>
          </div>
        </div>

        {/* Attendees */}
        <div className="space-y-3">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Attendees</p>
          {attendees.map((a, i) => (
            <div key={i} className="bg-gray-50 rounded-lg p-3 space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs font-medium text-gray-600">Person {i + 1}</span>
                {attendees.length > 1 && (
                  <button onClick={() => removeAttendee(i)}
                    className="text-xs text-gray-400 hover:text-red-500">remove</button>
                )}
              </div>
              <input placeholder="Full name" value={a.name}
                onChange={e => updateAttendee(i, "name", e.target.value)}
                className="w-full border border-gray-200 rounded px-2 py-1.5 text-xs text-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500"/>
              <input placeholder="email@company.com" value={a.email}
                onChange={e => updateAttendee(i, "email", e.target.value)}
                className="w-full border border-gray-200 rounded px-2 py-1.5 text-xs text-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500"/>
              <input placeholder="Company name" value={a.company}
                onChange={e => updateAttendee(i, "company", e.target.value)}
                className="w-full border border-gray-200 rounded px-2 py-1.5 text-xs text-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-500"/>
            </div>
          ))}
          <button onClick={addAttendee}
            className="w-full text-xs text-blue-600 border border-dashed border-blue-300 rounded-lg py-2 hover:bg-blue-50">
            + Add attendee
          </button>
        </div>

        {/* Generate button */}
        <button onClick={generate} disabled={loading || !title.trim()}
          className="w-full bg-blue-600 text-white rounded-xl py-3 text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors mt-auto">
          {loading ? "Generating..." : "Generate brief"}
        </button>
      </div>

      {/* ── Main area ────────────────────────────────────────────── */}
      <div className="flex-1 p-8 overflow-y-auto">

        {/* Empty state */}
        {!brief && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-14 h-14 bg-blue-50 rounded-2xl flex items-center justify-center mb-4">
              <svg className="w-7 h-7 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
              </svg>
            </div>
            <h2 className="text-lg font-medium text-gray-700 mb-2">Ready to prep</h2>
            <p className="text-sm text-gray-400 max-w-xs">
              Fill in the meeting details and attendees, then hit Generate brief. The AI researches each person and searches your meeting history automatically.
            </p>
          </div>
        )}

        {/* Loading state */}
        {loading && (
          <div className="flex flex-col items-center justify-center h-full gap-4">
            <div className="w-10 h-10 border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin"/>
            <p className="text-sm text-gray-500 max-w-sm text-center">{status}</p>
          </div>
        )}

        {/* Brief output */}
        {brief && !loading && (
          <div className="max-w-3xl">

            {/* Header */}
            <div className="mb-6">
              <div className="flex items-center gap-3 mb-1">
                <h2 className="text-xl font-semibold text-gray-900">{brief.meeting_title}</h2>
                <span className="text-xs px-2 py-1 bg-blue-50 text-blue-700 rounded-full font-medium">
                  {brief.meeting_type}
                </span>
              </div>
              <p className="text-sm text-gray-500">{brief.meeting_time} · {brief.meeting_type}</p>
            </div>

            {/* Metadata strip */}
            {meta && (
              <div className="flex gap-4 mb-6 p-3 bg-gray-50 rounded-xl">
                <div className="text-center">
                  <p className="text-lg font-semibold text-gray-900">{meta.attendees_researched}</p>
                  <p className="text-xs text-gray-400">researched</p>
                </div>
                <div className="w-px bg-gray-200"/>
                <div className="text-center">
                  <p className="text-lg font-semibold text-gray-900">{meta.past_meetings_found}</p>
                  <p className="text-xs text-gray-400">past meetings</p>
                </div>
                <div className="w-px bg-gray-200"/>
                <div className="text-center">
                  <p className="text-lg font-semibold text-gray-900">{meta.open_commitments}</p>
                  <p className="text-xs text-gray-400">open commitments</p>
                </div>
              </div>
            )}

            {/* Sections */}
            <div className="space-y-4">
              {sections.map((s, i) => (
                <div key={i} className="bg-white border border-gray-200 rounded-xl p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-base">{SECTION_ICONS[s.title] || "📌"}</span>
                    <h3 className="text-sm font-semibold text-gray-900">{s.title}</h3>
                  </div>
                  <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-line">
                    {s.content}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
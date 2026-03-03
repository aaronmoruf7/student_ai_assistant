"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { listTasks, getEvents, listConstraints, getUserProfile, importPlanEvents } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

type TaskRow = {
  name: string;
  course_name: string;
  due_at: string | null;
  remaining_minutes: number | null;
  status: string;
};

type EventRow = {
  title: string;
  start: string;
  end: string;
  all_day: boolean;
};

type Constraint = {
  constraint_type: string;
  start_time?: string | null;
  end_time?: string | null;
  is_active: boolean;
};

type ParsedEvent = {
  title: string;
  start: string;
  end: string;
  description: string;
};

// ─── Date helpers ─────────────────────────────────────────────────────────────

function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

function startOfDay(date: Date): Date {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  return d;
}

function fmtDate(date: Date): string {
  return date.toLocaleDateString("en-US", {
    weekday: "short", month: "short", day: "numeric", year: "numeric",
  });
}

function fmtDateShort(date: Date): string {
  return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function fmtTime(date: Date): string {
  return date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
}

function fmtHour(h: number, m: number): string {
  const d = new Date(); d.setHours(h, m, 0, 0);
  return fmtTime(d);
}

function durationH(ms: number): string {
  return (ms / 3600000).toFixed(1) + "h";
}

function fmtDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return durationH(ms);
}

// ─── Formatting functions (same logic as Data Hub) ────────────────────────────

function formatTasks(
  groups: { course_name: string; tasks: TaskRow[] }[],
  weeks: number
): string {
  const today = startOfDay(new Date());
  const cutoff = addDays(today, weeks * 7);
  const lines: string[] = [
    `=== ASSIGNMENTS (Next ${weeks} week${weeks > 1 ? "s" : ""}: ${fmtDate(today)} – ${fmtDate(cutoff)}) ===`,
    "",
  ];

  const undated: (TaskRow & { course_name: string })[] = [];
  let hasAny = false;

  for (const group of groups) {
    const inRange: TaskRow[] = [];
    for (const t of group.tasks) {
      if (t.status === "completed") continue;
      if (!t.due_at) { undated.push({ ...t, course_name: group.course_name }); continue; }
      const due = new Date(t.due_at);
      if (due >= today && due <= cutoff) inRange.push(t);
    }
    if (inRange.length === 0) continue;
    hasAny = true;
    lines.push(`COURSE: ${group.course_name}`);
    for (const t of inRange) {
      const due = fmtDateShort(new Date(t.due_at!));
      const rem = t.remaining_minutes != null
        ? `${(t.remaining_minutes / 60).toFixed(1)}h remaining`
        : "no estimate";
      lines.push(`  - [${t.status === "in_progress" ? "IN PROGRESS" : "TODO"}] ${t.name} | Due: ${due} | ${rem}`);
    }
    lines.push("");
  }

  if (undated.length > 0) {
    hasAny = true;
    lines.push("UNDATED / RECURRING TASKS:");
    for (const t of undated) {
      const rem = t.remaining_minutes != null
        ? `${(t.remaining_minutes / 60).toFixed(1)}h per instance`
        : "no estimate";
      lines.push(`  - ${t.name} (${t.course_name}) | No due date | ${rem}`);
    }
    lines.push("");
  }

  if (!hasAny) lines.push("  (No pending assignments in this window)");
  return lines.join("\n").trim();
}

function formatCalendar(
  events: EventRow[],
  constraints: Constraint[],
  weeks: number
): string {
  const today = startOfDay(new Date());
  const cutoff = addDays(today, weeks * 7);

  const sleep = constraints.find((c) => c.constraint_type === "sleep" && c.is_active);
  let wakeH = 7, wakeM = 0, sleepH = 23, sleepM = 0;
  if (sleep) {
    if (sleep.end_time) { const [h, m] = sleep.end_time.split(":").map(Number); wakeH = h; wakeM = m; }
    if (sleep.start_time) { const [h, m] = sleep.start_time.split(":").map(Number); sleepH = h; sleepM = m; }
  }

  const lines: string[] = [
    `=== CALENDAR — FREE TIME (Next ${weeks} week${weeks > 1 ? "s" : ""}: ${fmtDate(today)} – ${fmtDate(cutoff)}) ===`,
    `(Waking hours: ${fmtHour(wakeH, wakeM)} – ${fmtHour(sleepH, sleepM)})`,
    "",
  ];

  for (let d = new Date(today); d < cutoff; d = addDays(d, 1)) {
    const dayStart = new Date(d); dayStart.setHours(wakeH, wakeM, 0, 0);
    const dayEnd = new Date(d); dayEnd.setHours(sleepH, sleepM, 0, 0);
    // If sleep time is midnight or early AM, dayEnd ends up before dayStart —
    // push it to the same wall-clock time on the next calendar day.
    if (dayEnd <= dayStart) dayEnd.setDate(dayEnd.getDate() + 1);

    const dayEvents = events
      .filter((e) => {
        if (e.all_day) return false;
        const es = new Date(e.start), ee = new Date(e.end);
        return es < dayEnd && ee > dayStart;
      })
      .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime());

    lines.push(fmtDateShort(d) + ":");

    if (dayEvents.length > 0) {
      lines.push(`  Busy: ${dayEvents.map((e) => `${fmtTime(new Date(e.start))}–${fmtTime(new Date(e.end))} (${e.title})`).join(", ")}`);
    } else {
      lines.push("  Busy: none");
    }

    const free: { start: Date; end: Date }[] = [];
    let cursor = dayStart;
    for (const e of dayEvents) {
      const es = new Date(e.start) < dayStart ? dayStart : new Date(e.start);
      const ee = new Date(e.end) > dayEnd ? dayEnd : new Date(e.end);
      if (es > cursor && es.getTime() - cursor.getTime() >= 30 * 60000)
        free.push({ start: new Date(cursor), end: es });
      if (ee > cursor) cursor = ee;
    }
    if (dayEnd > cursor && dayEnd.getTime() - cursor.getTime() >= 30 * 60000)
      free.push({ start: new Date(cursor), end: dayEnd });

    if (free.length > 0) {
      const totalMs = free.reduce((s, f) => s + f.end.getTime() - f.start.getTime(), 0);
      lines.push(`  Free: ${free.map((f) => `${fmtTime(f.start)}–${fmtTime(f.end)} (${durationH(f.end.getTime() - f.start.getTime())})`).join(", ")}`);
      lines.push(`  Total available: ${durationH(totalMs)}`);
    } else {
      lines.push("  Free: none (fully booked)");
    }
    lines.push("");
  }

  return lines.join("\n").trim();
}

// ─── Build the full planning prompt ──────────────────────────────────────────

function buildPlanPrompt(
  groups: { course_name: string; tasks: TaskRow[] }[],
  events: EventRow[],
  constraints: Constraint[],
  preferences: string | null,
  weeks: number
): string {
  const today = new Date();
  const taskSection = formatTasks(groups, weeks);
  const calSection = formatCalendar(events, constraints, weeks);

  const parts: string[] = [
    `You are a student schedule planner. Create a realistic, specific study plan based on the data below.`,
    `Today is ${fmtDate(today)}. Plan for the next ${weeks} week${weeks > 1 ? "s" : ""}.`,
    "",
    taskSection,
    "",
    calSection,
  ];

  if (preferences?.trim()) {
    parts.push("", "=== MY PREFERENCES ===", "", preferences.trim());
  }

  parts.push(
    "",
    "---",
    "PLANNING RULES:",
    "1. Only schedule sessions during the FREE slots listed in the calendar section. Do not place events during busy times.",
    "2. Do not stack all work in the week something is due. Spread it out — start tasks 5–10 days before the due date, especially for large assignments.",
    "3. Follow my preferences: session length, break frequency, and peak productivity hours.",
    "4. Be specific in descriptions (e.g. \"Complete questions 3–6 of HW2\", not just \"Study\").",
    "5. Leave some buffer — don't fill every available slot.",
    "6. Prioritize tasks with the closest due dates and highest remaining effort.",
    "",
    "OUTPUT INSTRUCTIONS:",
    "Return ONLY a valid JSON array — no explanation, no markdown code fences, no other text. Just the raw JSON:",
    "",
    "[",
    "  {",
    "    \"title\": \"Study: CS 301 — Binary Trees HW\",",
    "    \"start\": \"YYYY-MM-DDTHH:MM:SS\",",
    "    \"end\": \"YYYY-MM-DDTHH:MM:SS\",",
    "    \"description\": \"Complete questions 1–4\"",
    "  }",
    "]",
    "",
    "JSON rules:",
    "- Use 24-hour ISO 8601 format with no timezone suffix: YYYY-MM-DDTHH:MM:SS",
    "- Title format: \"Study: [Course] — [Task name]\"",
    "- Events must not overlap with busy times or each other",
    "- Events must fall within waking hours",
  );

  return parts.join("\n");
}

// ─── JSON parser ──────────────────────────────────────────────────────────────

function parseEventsFromText(text: string): { events: ParsedEvent[]; error: string | null } {
  const start = text.indexOf("[");
  const end = text.lastIndexOf("]");

  if (start === -1 || end === -1 || end <= start) {
    return { events: [], error: "No JSON array found. Make sure you copied the full LLM output." };
  }

  try {
    const parsed = JSON.parse(text.slice(start, end + 1));
    if (!Array.isArray(parsed)) {
      return { events: [], error: "Expected a JSON array but got something else." };
    }

    const events: ParsedEvent[] = [];
    for (const item of parsed) {
      if (!item.title || !item.start || !item.end) {
        return { events: [], error: `Event is missing required fields (title, start, end): ${JSON.stringify(item)}` };
      }
      events.push({
        title: String(item.title),
        start: String(item.start),
        end: String(item.end),
        description: String(item.description || ""),
      });
    }

    return { events, error: null };
  } catch {
    return { events: [], error: "Invalid JSON. Make sure you copied the complete array including the opening [ and closing ]." };
  }
}

// ─── Copy button ─────────────────────────────────────────────────────────────

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      }}
      className="px-3 py-1.5 text-sm border border-slate-300 rounded hover:border-slate-500 transition-colors whitespace-nowrap"
    >
      {copied ? "✓ Copied" : label}
    </button>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PlanPage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  const [weeks, setWeeks] = useState(2);
  const [groups, setGroups] = useState<{ course_name: string; tasks: TaskRow[] }[]>([]);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [constraints, setConstraints] = useState<Constraint[]>([]);
  const [preferences, setPreferences] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [pasted, setPasted] = useState("");
  const [parsedEvents, setParsedEvents] = useState<ParsedEvent[] | null>(null);
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const [parseError, setParseError] = useState<string | null>(null);

  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<{ created: number; errors: { title: string; error: string }[] } | null>(null);

  useEffect(() => {
    if (status === "unauthenticated") router.push("/login");
  }, [status, router]);

  const userId = (session?.user as any)?.id;

  useEffect(() => {
    if (!userId) return;
    Promise.all([
      listTasks(userId),
      getEvents(userId),
      listConstraints(userId),
      getUserProfile(userId),
    ])
      .then(([t, e, c, p]) => {
        setGroups(t.groups);
        setEvents(e.events);
        setConstraints(c.constraints);
        setPreferences(p.ai_preferences);
      })
      .finally(() => setLoading(false));
  }, [userId]);

  const planPrompt = buildPlanPrompt(groups, events, constraints, preferences, weeks);

  function handleParse() {
    setImportResult(null);
    const { events: parsed, error } = parseEventsFromText(pasted);
    if (parsed.length > 0) {
      setParsedEvents(parsed);
      setSelectedIndices(new Set(parsed.map((_, i) => i)));
    } else {
      setParsedEvents(null);
      setSelectedIndices(new Set());
    }
    setParseError(error);
  }

  function toggleIndex(i: number) {
    setSelectedIndices((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }

  function toggleAll() {
    if (!parsedEvents) return;
    if (selectedIndices.size === parsedEvents.length) {
      setSelectedIndices(new Set());
    } else {
      setSelectedIndices(new Set(parsedEvents.map((_, i) => i)));
    }
  }

  async function handleImport() {
    if (!userId || !parsedEvents || selectedIndices.size === 0) return;
    const toImport = parsedEvents.filter((_, i) => selectedIndices.has(i));
    setImporting(true);
    setImportResult(null);
    try {
      const result = await importPlanEvents(userId, toImport);
      setImportResult(result);
      if (result.created > 0) {
        setPasted("");
        setParsedEvents(null);
        setSelectedIndices(new Set());
      }
    } finally {
      setImporting(false);
    }
  }

  if (status === "loading" || loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-400">
        Loading...
      </div>
    );
  }

  if (!session) return null;

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="border-b bg-white sticky top-0 z-10">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-slate-500 hover:text-slate-700 text-sm">← Dashboard</Link>
            <h1 className="font-semibold text-lg">Plan</h1>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-500 mr-1">Plan next:</span>
            {[1, 2, 3, 4].map((w) => (
              <button
                key={w}
                onClick={() => setWeeks(w)}
                className={`px-3 py-1 rounded text-sm border transition-colors ${
                  weeks === w
                    ? "bg-slate-800 text-white border-slate-800"
                    : "border-slate-300 text-slate-600 hover:border-slate-500"
                }`}
              >
                {w}w
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6 space-y-5 max-w-4xl">

        {/* Step 1 — Planning prompt */}
        <section className="bg-white rounded-lg border">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <div>
              <h2 className="font-semibold text-slate-800">Step 1 — Copy this prompt into your LLM</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Contains your assignments, free time slots, and preferences. Paste into ChatGPT or Claude.
              </p>
            </div>
            <CopyButton text={planPrompt} label="Copy Prompt" />
          </div>
          <pre className="p-4 text-xs text-slate-700 font-mono whitespace-pre-wrap overflow-auto max-h-96 leading-relaxed">
            {planPrompt}
          </pre>
        </section>

        {/* Step 2 — Paste LLM output */}
        <section className="bg-white rounded-lg border">
          <div className="px-4 py-3 border-b">
            <h2 className="font-semibold text-slate-800">Step 2 — Paste the LLM's JSON output here</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              The LLM should return a raw JSON array. Paste the entire response and click Parse.
            </p>
          </div>
          <div className="p-4 space-y-3">
            <textarea
              value={pasted}
              onChange={(e) => {
                setPasted(e.target.value);
                setParsedEvents(null);
                setParseError(null);
                setImportResult(null);
              }}
              placeholder='[ { "title": "Study: CS 301 — HW3", "start": "2026-03-04T10:00:00", "end": "2026-03-04T11:30:00", "description": "..." } ]'
              rows={8}
              className="w-full text-sm font-mono border border-slate-200 rounded-lg p-3 resize-y focus:outline-none focus:border-slate-400 text-slate-700 placeholder:text-slate-300"
            />
            <button
              onClick={handleParse}
              disabled={!pasted.trim()}
              className="px-4 py-2 bg-slate-700 text-white text-sm rounded hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Parse Events
            </button>
            {parseError && (
              <p className="text-sm text-red-500">{parseError}</p>
            )}
          </div>
        </section>

        {/* Step 3 — Preview + import */}
        {parsedEvents && parsedEvents.length > 0 && (
          <section className="bg-white rounded-lg border">
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <div>
                <h2 className="font-semibold text-slate-800">
                  Step 3 — Review and add to Google Calendar
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  {selectedIndices.size} of {parsedEvents.length} event{parsedEvents.length > 1 ? "s" : ""} selected.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={toggleAll}
                  className="px-3 py-1.5 text-sm border border-slate-300 rounded hover:border-slate-500 transition-colors"
                >
                  {selectedIndices.size === parsedEvents.length ? "Deselect All" : "Select All"}
                </button>
                <button
                  onClick={handleImport}
                  disabled={importing || selectedIndices.size === 0}
                  className="px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {importing ? "Adding..." : `Add ${selectedIndices.size} to Calendar`}
                </button>
              </div>
            </div>

            {/* Event checklist table */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                    <th className="px-4 py-2 w-8"></th>
                    <th className="text-left px-4 py-2">Title</th>
                    <th className="text-left px-4 py-2">Start</th>
                    <th className="text-left px-4 py-2">End</th>
                    <th className="text-left px-4 py-2">Duration</th>
                    <th className="text-left px-4 py-2">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {parsedEvents.map((ev, i) => {
                    const checked = selectedIndices.has(i);
                    return (
                      <tr
                        key={i}
                        onClick={() => toggleIndex(i)}
                        className={`border-b last:border-0 cursor-pointer transition-colors ${
                          checked ? "hover:bg-slate-50" : "bg-slate-50 opacity-50 hover:opacity-70"
                        }`}
                      >
                        <td className="px-4 py-2">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleIndex(i)}
                            onClick={(e) => e.stopPropagation()}
                            className="h-4 w-4 rounded border-slate-300 cursor-pointer"
                          />
                        </td>
                        <td className="px-4 py-2 font-medium text-slate-800">{ev.title}</td>
                        <td className="px-4 py-2 text-slate-600 whitespace-nowrap">
                          {fmtDateShort(new Date(ev.start))} {fmtTime(new Date(ev.start))}
                        </td>
                        <td className="px-4 py-2 text-slate-600 whitespace-nowrap">
                          {fmtTime(new Date(ev.end))}
                        </td>
                        <td className="px-4 py-2 text-slate-500">{fmtDuration(ev.start, ev.end)}</td>
                        <td className="px-4 py-2 text-slate-500 max-w-xs truncate">{ev.description}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Import result */}
            {importResult && (
              <div className="px-4 py-3 border-t">
                {importResult.created > 0 && (
                  <p className="text-sm text-green-600">
                    ✓ {importResult.created} event{importResult.created > 1 ? "s" : ""} added to Google Calendar.
                  </p>
                )}
                {importResult.errors.length > 0 && (
                  <div className="mt-1 space-y-1">
                    {importResult.errors.map((e, i) => (
                      <p key={i} className="text-xs text-red-500">
                        Failed: {e.title} — {e.error}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {/* Tip */}
        {!preferences && (
          <div className="bg-amber-50 border border-amber-200 text-amber-700 rounded-lg px-4 py-3 text-sm">
            Tip: You don't have preferences saved yet. Add them on the{" "}
            <Link href="/preferences" className="underline">Preferences page</Link>{" "}
            for a better planning prompt.
          </div>
        )}
      </main>
    </div>
  );
}

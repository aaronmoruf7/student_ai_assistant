"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { listTasks, getEvents, listConstraints, getUserProfile } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

type TaskRow = {
  id: string;
  name: string;
  course_name: string;
  due_at: string | null;
  remaining_minutes: number | null;
  status: string;
};

type EventRow = {
  id: string;
  title: string;
  start: string;
  end: string;
  all_day: boolean;
  event_type: string;
};

type Constraint = {
  id: string;
  constraint_type: string;
  name: string;
  start_time?: string | null;
  end_time?: string | null;
  is_active: boolean;
};

// ─── Formatting helpers ───────────────────────────────────────────────────────

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
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function fmtDateShort(date: Date): string {
  return date.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function fmtTime(date: Date): string {
  return date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function fmtHour(h: number, m: number): string {
  const d = new Date();
  d.setHours(h, m, 0, 0);
  return fmtTime(d);
}

function durationH(ms: number): string {
  return (ms / 3600000).toFixed(1) + "h";
}

// ─── Format tasks for LLM ────────────────────────────────────────────────────

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
      if (!t.due_at) {
        undated.push({ ...t, course_name: group.course_name });
        continue;
      }
      const due = new Date(t.due_at);
      if (due >= today && due <= cutoff) inRange.push(t);
    }

    if (inRange.length === 0) continue;
    hasAny = true;

    lines.push(`COURSE: ${group.course_name}`);
    for (const t of inRange) {
      const due = fmtDateShort(new Date(t.due_at!));
      const rem =
        t.remaining_minutes != null
          ? `${(t.remaining_minutes / 60).toFixed(1)}h remaining`
          : "no estimate";
      const label = t.status === "in_progress" ? "IN PROGRESS" : "TODO";
      lines.push(`  - [${label}] ${t.name} | Due: ${due} | ${rem}`);
    }
    lines.push("");
  }

  if (undated.length > 0) {
    hasAny = true;
    lines.push("UNDATED / RECURRING TASKS:");
    for (const t of undated) {
      const rem =
        t.remaining_minutes != null
          ? `${(t.remaining_minutes / 60).toFixed(1)}h per instance`
          : "no estimate";
      lines.push(`  - ${t.name} (${t.course_name}) | No due date | ${rem}`);
    }
    lines.push("");
  }

  if (!hasAny) {
    lines.push("  (No pending assignments in this window)");
  }

  return lines.join("\n").trim();
}

// ─── Format calendar + free slots for LLM ────────────────────────────────────

function formatCalendar(
  events: EventRow[],
  constraints: Constraint[],
  weeks: number
): string {
  const today = startOfDay(new Date());
  const cutoff = addDays(today, weeks * 7);

  // Determine waking hours from sleep constraint
  const sleep = constraints.find(
    (c) => c.constraint_type === "sleep" && c.is_active
  );
  let wakeH = 7, wakeM = 0, sleepH = 23, sleepM = 0;
  if (sleep) {
    if (sleep.end_time) {
      const [h, m] = sleep.end_time.split(":").map(Number);
      wakeH = h; wakeM = m;
    }
    if (sleep.start_time) {
      const [h, m] = sleep.start_time.split(":").map(Number);
      sleepH = h; sleepM = m;
    }
  }

  const lines: string[] = [
    `=== CALENDAR (Next ${weeks} week${weeks > 1 ? "s" : ""}: ${fmtDate(today)} – ${fmtDate(cutoff)}) ===`,
    `(Waking hours: ${fmtHour(wakeH, wakeM)} – ${fmtHour(sleepH, sleepM)})`,
    "",
  ];

  for (let d = new Date(today); d < cutoff; d = addDays(d, 1)) {
    const dayStart = new Date(d);
    dayStart.setHours(wakeH, wakeM, 0, 0);
    const dayEnd = new Date(d);
    dayEnd.setHours(sleepH, sleepM, 0, 0);
    // If sleep time is midnight or early AM, dayEnd ends up before dayStart —
    // push it to the same wall-clock time on the next calendar day.
    if (dayEnd <= dayStart) dayEnd.setDate(dayEnd.getDate() + 1);

    // Events overlapping this day's waking window (skip all-day)
    const dayEvents = events
      .filter((e) => {
        if (e.all_day) return false;
        const es = new Date(e.start);
        const ee = new Date(e.end);
        return es < dayEnd && ee > dayStart;
      })
      .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime());

    lines.push(fmtDateShort(d) + ":");

    if (dayEvents.length > 0) {
      const busyStr = dayEvents
        .map((e) => {
          const es = new Date(e.start);
          const ee = new Date(e.end);
          return `${fmtTime(es)}–${fmtTime(ee)} (${e.title})`;
        })
        .join(", ");
      lines.push(`  Busy: ${busyStr}`);
    } else {
      lines.push(`  Busy: none`);
    }

    // Compute free slots
    const free: { start: Date; end: Date }[] = [];
    let cursor = dayStart;

    for (const e of dayEvents) {
      const es = new Date(e.start) < dayStart ? dayStart : new Date(e.start);
      const ee = new Date(e.end) > dayEnd ? dayEnd : new Date(e.end);
      if (es > cursor) {
        const gap = es.getTime() - cursor.getTime();
        if (gap >= 30 * 60000) free.push({ start: new Date(cursor), end: es });
      }
      if (ee > cursor) cursor = ee;
    }
    if (dayEnd > cursor) {
      const gap = dayEnd.getTime() - cursor.getTime();
      if (gap >= 30 * 60000) free.push({ start: new Date(cursor), end: dayEnd });
    }

    if (free.length > 0) {
      const totalMs = free.reduce((s, f) => s + (f.end.getTime() - f.start.getTime()), 0);
      const freeStr = free
        .map((f) => `${fmtTime(f.start)}–${fmtTime(f.end)} (${durationH(f.end.getTime() - f.start.getTime())})`)
        .join(", ");
      lines.push(`  Free: ${freeStr}`);
      lines.push(`  Total available: ${durationH(totalMs)}`);
    } else {
      lines.push(`  Free: none (fully booked)`);
    }

    lines.push("");
  }

  return lines.join("\n").trim();
}

// ─── Copy button ─────────────────────────────────────────────────────────────

function CopyButton({
  text,
  label = "Copy",
}: {
  text: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="px-3 py-1 text-sm border border-slate-300 rounded hover:border-slate-500 transition-colors"
    >
      {copied ? "✓ Copied" : label}
    </button>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DataPage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  const [weeks, setWeeks] = useState(4);
  const [groups, setGroups] = useState<{ course_name: string; tasks: TaskRow[] }[]>([]);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [constraints, setConstraints] = useState<Constraint[]>([]);
  const [preferences, setPreferences] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "unauthenticated") router.push("/login");
  }, [status, router]);

  const userId = (session?.user as any)?.id;

  useEffect(() => {
    if (!userId) return;
    setLoading(true);
    setError(null);

    Promise.all([
      listTasks(userId),
      getEvents(userId),
      listConstraints(userId),
      getUserProfile(userId),
    ])
      .then(([tasksRes, eventsRes, constraintsRes, profileRes]) => {
        setGroups(tasksRes.groups);
        setEvents(eventsRes.events);
        setConstraints(constraintsRes.constraints);
        setPreferences(profileRes.ai_preferences);
      })
      .catch(() => setError("Failed to load data. Try syncing from the dashboard first."))
      .finally(() => setLoading(false));
  }, [userId]);

  if (status === "loading" || loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-400">
        Loading...
      </div>
    );
  }

  if (!session) return null;

  const taskText = formatTasks(groups, weeks);
  const calText = formatCalendar(events, constraints, weeks);
  const prefsSection = preferences
    ? `=== USER PREFERENCES ===\n\n${preferences}`
    : null;

  const allText = [taskText, calText, prefsSection]
    .filter(Boolean)
    .join("\n\n\n");

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="border-b bg-white sticky top-0 z-10">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-slate-500 hover:text-slate-700 text-sm">
              ← Dashboard
            </Link>
            <h1 className="font-semibold text-lg">Data Hub</h1>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-500 mr-1">Show next:</span>
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
            <div className="ml-3">
              <CopyButton text={allText} label="Copy All" />
            </div>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6 space-y-5 max-w-4xl">
        {error && (
          <div className="bg-amber-50 border border-amber-200 text-amber-700 rounded-lg px-4 py-3 text-sm">
            {error}
          </div>
        )}

        {events.length === 0 && !error && (
          <div className="bg-blue-50 border border-blue-200 text-blue-700 rounded-lg px-4 py-3 text-sm">
            Calendar is empty. Use the <strong>Sync</strong> button on the dashboard to pull your Google Calendar events first.
          </div>
        )}

        {/* Assignments */}
        <section className="bg-white rounded-lg border">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <div>
              <h2 className="font-semibold text-slate-800">Assignments</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Pending tasks due within {weeks} week{weeks > 1 ? "s" : ""}, plus undated/recurring
              </p>
            </div>
            <CopyButton text={taskText} />
          </div>
          <pre className="p-4 text-xs text-slate-700 font-mono whitespace-pre-wrap overflow-auto max-h-96 leading-relaxed">
            {taskText}
          </pre>
        </section>

        {/* Calendar */}
        <section className="bg-white rounded-lg border">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <div>
              <h2 className="font-semibold text-slate-800">Calendar</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Busy blocks and pre-computed free slots per day
              </p>
            </div>
            <CopyButton text={calText} />
          </div>
          <pre className="p-4 text-xs text-slate-700 font-mono whitespace-pre-wrap overflow-auto max-h-96 leading-relaxed">
            {calText}
          </pre>
        </section>

        {/* Preferences */}
        <section className="bg-white rounded-lg border">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <div>
              <h2 className="font-semibold text-slate-800">Preferences</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Your goals, work style, and commitments
              </p>
            </div>
            {preferences && (
              <CopyButton text={`=== USER PREFERENCES ===\n\n${preferences}`} />
            )}
          </div>

          {preferences ? (
            <pre className="p-4 text-xs text-slate-700 font-mono whitespace-pre-wrap overflow-auto max-h-60 leading-relaxed">
              {preferences}
            </pre>
          ) : (
            <div className="p-8 text-center text-slate-400 text-sm">
              <p className="mb-2">No preferences saved yet.</p>
              <Link href="/preferences" className="text-blue-600 hover:underline">
                Set up your preferences →
              </Link>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

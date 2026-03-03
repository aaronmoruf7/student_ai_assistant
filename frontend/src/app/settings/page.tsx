"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";

import {
  listConstraints,
  createConstraint,
  updateConstraint,
  deleteConstraint,
  type ConstraintOut,
} from "@/lib/api";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const WEEKDAYS = [0, 1, 2, 3, 4];
const WEEKEND = [5, 6];
const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function daysLabel(days: number[] | null | undefined): string {
  if (!days) return "";
  const s = new Set(days);
  if (ALL_DAYS.every((d) => s.has(d))) return "Every day";
  if (WEEKDAYS.every((d) => s.has(d)) && !s.has(5) && !s.has(6)) return "Weekdays";
  if (WEEKEND.every((d) => s.has(d)) && !s.has(0)) return "Weekends";
  return days.map((d) => DAYS[d]).join(", ");
}

// ---------------------------------------------------------------------------
// Form for creating / editing a constraint
// ---------------------------------------------------------------------------

type FormState = {
  constraint_type: string;
  name: string;
  start_time: string;
  end_time: string;
  days_of_week: number[];
  max_minutes: string;
  is_active: boolean;
};

const EMPTY_FORM: FormState = {
  constraint_type: "sleep",
  name: "",
  start_time: "",
  end_time: "",
  days_of_week: ALL_DAYS,
  max_minutes: "",
  is_active: true,
};

function ConstraintForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: FormState;
  onSave: (f: FormState) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<FormState>(initial ?? EMPTY_FORM);

  const set = (key: keyof FormState, value: unknown) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const toggleDay = (d: number) => {
    const next = form.days_of_week.includes(d)
      ? form.days_of_week.filter((x) => x !== d)
      : [...form.days_of_week, d].sort();
    set("days_of_week", next);
  };

  const setDayPreset = (days: number[]) => set("days_of_week", days);

  const needsTime = ["sleep", "meal", "blocked_time"].includes(form.constraint_type);
  const needsMax = form.constraint_type === "max_hours_per_day";

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 space-y-4">
      {/* Type */}
      <div className="flex gap-3 flex-wrap">
        {[
          { value: "sleep", label: "Sleep" },
          { value: "meal", label: "Meal / Break" },
          { value: "blocked_time", label: "Protected time" },
          { value: "max_hours_per_day", label: "Max hours/day" },
        ].map((opt) => (
          <button
            key={opt.value}
            onClick={() => set("constraint_type", opt.value)}
            className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
              form.constraint_type === opt.value
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white text-slate-600 border-slate-300 hover:border-slate-400"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Name */}
      <div>
        <label className="text-xs text-slate-500 mb-1 block">Label</label>
        <input
          type="text"
          placeholder={form.constraint_type === "sleep" ? "Sleep" : "e.g. Lunch break"}
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
          className="border border-slate-300 rounded px-3 py-1.5 text-sm w-full"
        />
      </div>

      {/* Time range */}
      {needsTime && (
        <div className="flex gap-3 items-center">
          <div>
            <label className="text-xs text-slate-500 mb-1 block">
              {form.constraint_type === "sleep" ? "Sleep time" : "Start"}
            </label>
            <input
              type="time"
              value={form.start_time}
              onChange={(e) => set("start_time", e.target.value)}
              className="border border-slate-300 rounded px-2 py-1.5 text-sm"
            />
          </div>
          <span className="text-slate-400 mt-5">→</span>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">
              {form.constraint_type === "sleep" ? "Wake time" : "End"}
            </label>
            <input
              type="time"
              value={form.end_time}
              onChange={(e) => set("end_time", e.target.value)}
              className="border border-slate-300 rounded px-2 py-1.5 text-sm"
            />
          </div>
        </div>
      )}

      {/* Max hours */}
      {needsMax && (
        <div>
          <label className="text-xs text-slate-500 mb-1 block">Max study hours per day</label>
          <input
            type="number"
            min="1"
            max="16"
            step="0.5"
            value={form.max_minutes}
            onChange={(e) => set("max_minutes", e.target.value)}
            className="border border-slate-300 rounded px-3 py-1.5 text-sm w-28"
          />
        </div>
      )}

      {/* Days of week */}
      {needsTime && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <label className="text-xs text-slate-500">Days</label>
            <button onClick={() => setDayPreset(ALL_DAYS)} className="text-xs text-blue-500 hover:underline">All</button>
            <button onClick={() => setDayPreset(WEEKDAYS)} className="text-xs text-blue-500 hover:underline">Weekdays</button>
            <button onClick={() => setDayPreset(WEEKEND)} className="text-xs text-blue-500 hover:underline">Weekends</button>
          </div>
          <div className="flex gap-1">
            {DAYS.map((label, i) => (
              <button
                key={i}
                onClick={() => toggleDay(i)}
                className={`w-9 h-9 rounded-full text-xs font-medium border transition-colors ${
                  form.days_of_week.includes(i)
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-white text-slate-500 border-slate-300 hover:border-slate-400"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-1">
        <button
          onClick={() => onSave(form)}
          className="px-4 py-1.5 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700"
        >
          Save
        </button>
        <button onClick={onCancel} className="px-4 py-1.5 text-slate-500 text-sm hover:underline">
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  const [constraints, setConstraints] = useState<ConstraintOut[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const userId = session?.user?.id;

  useEffect(() => {
    if (status === "unauthenticated") router.push("/login");
  }, [status, router]);

  useEffect(() => {
    if (!userId) return;
    listConstraints(userId).then((d) => {
      setConstraints(d.constraints);
      setIsLoading(false);
    });
  }, [userId]);

  const reload = () =>
    userId && listConstraints(userId).then((d) => setConstraints(d.constraints));

  const formToPayload = (f: FormState) => ({
    constraint_type: f.constraint_type,
    name: f.name || f.constraint_type,
    days_of_week: f.days_of_week.length > 0 ? f.days_of_week : ALL_DAYS,
    start_time: f.start_time || null,
    end_time: f.end_time || null,
    max_minutes: f.max_minutes ? Math.round(parseFloat(f.max_minutes) * 60) : null,
    is_active: f.is_active,
  });

  const handleCreate = async (f: FormState) => {
    if (!userId) return;
    await createConstraint(userId, formToPayload(f));
    setAdding(false);
    await reload();
  };

  const handleUpdate = async (id: string, f: FormState) => {
    if (!userId) return;
    await updateConstraint(userId, id, formToPayload(f));
    setEditingId(null);
    await reload();
  };

  const handleDelete = async (id: string) => {
    if (!userId) return;
    await deleteConstraint(userId, id);
    await reload();
  };

  const toFormState = (c: ConstraintOut): FormState => ({
    constraint_type: c.constraint_type,
    name: c.name,
    start_time: c.start_time ?? "",
    end_time: c.end_time ?? "",
    days_of_week: c.days_of_week ?? ALL_DAYS,
    max_minutes: c.max_minutes ? String(c.max_minutes / 60) : "",
    is_active: c.is_active,
  });

  if (status === "loading" || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <p className="text-slate-500">Loading...</p>
      </div>
    );
  }

  if (!session) return null;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-slate-500 hover:text-slate-700 text-sm">← Dashboard</Link>
            <h1 className="font-semibold text-lg">Settings</h1>
          </div>
          <p className="text-sm text-slate-500">Your schedule constraints</p>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6 max-w-2xl space-y-6">

        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-slate-800">Schedule constraints</h2>
            <p className="text-sm text-slate-500 mt-0.5">
              Tell the planner when you sleep, eat, and can't be disturbed.
            </p>
          </div>
          {!adding && (
            <button
              onClick={() => setAdding(true)}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700"
            >
              + Add
            </button>
          )}
        </div>

        {adding && (
          <ConstraintForm onSave={handleCreate} onCancel={() => setAdding(false)} />
        )}

        {constraints.length === 0 && !adding && (
          <div className="text-center py-12 text-slate-400">
            <p>No constraints yet.</p>
            <p className="text-sm mt-1">Add your sleep schedule to get a realistic plan.</p>
          </div>
        )}

        <div className="space-y-3">
          {constraints.map((c) =>
            editingId === c.id ? (
              <ConstraintForm
                key={c.id}
                initial={toFormState(c)}
                onSave={(f) => handleUpdate(c.id, f)}
                onCancel={() => setEditingId(null)}
              />
            ) : (
              <div
                key={c.id}
                className={`bg-white border rounded-lg px-4 py-3 flex items-center gap-4 ${
                  c.is_active ? "border-slate-200" : "border-slate-100 opacity-50"
                }`}
              >
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-slate-800 text-sm">{c.name}</p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {c.start_time && c.end_time
                      ? `${c.start_time} → ${c.end_time}`
                      : c.max_minutes
                      ? `Max ${c.max_minutes / 60} hrs/day`
                      : ""}
                    {c.days_of_week && (
                      <span className="ml-2 text-slate-300">·</span>
                    )}{" "}
                    {daysLabel(c.days_of_week)}
                  </p>
                </div>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 capitalize shrink-0">
                  {c.constraint_type.replace("_", " ")}
                </span>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => setEditingId(c.id)}
                    className="text-xs text-slate-400 hover:text-slate-700"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(c.id)}
                    className="text-xs text-slate-300 hover:text-red-500"
                  >
                    Delete
                  </button>
                </div>
              </div>
            )
          )}
        </div>
      </main>
    </div>
  );
}

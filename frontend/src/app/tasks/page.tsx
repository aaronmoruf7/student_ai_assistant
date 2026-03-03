"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState, useRef } from "react";
import Link from "next/link";

import { listTasks, createTask, updateTask, deleteTask, getSetupCourses } from "@/lib/api";

type TaskRow = {
  id: string;
  name: string;
  course_name: string;
  course_id: string | null;
  due_at: string | null;
  source: "canvas" | "extracted" | "manual";
  estimated_minutes: number | null;
  user_estimated_minutes: number | null;
  completed_minutes: number;
  remaining_minutes: number | null;
  status: string;
  confidence: number | null;
};

type CourseGroup = {
  course_name: string;
  tasks: TaskRow[];
};

type Course = {
  canvas_course_id: number;
  name: string;
  internal_id: string | null;
};

const SOURCE_BADGE: Record<string, string> = {
  canvas: "bg-blue-100 text-blue-700",
  extracted: "bg-purple-100 text-purple-700",
  manual: "bg-green-100 text-green-700",
};

const STATUS_OPTIONS = ["pending", "in_progress", "completed"];

function toHours(minutes: number | null | undefined): string {
  if (!minutes) return "";
  const h = minutes / 60;
  return h % 1 === 0 ? String(h) : h.toFixed(1);
}

function fromHours(value: string): number | null {
  const n = parseFloat(value);
  if (isNaN(n) || n <= 0) return null;
  return Math.round(n * 60);
}

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return iso.slice(0, 10); // YYYY-MM-DD
}

// ---------------------------------------------------------------------------
// Inline editable cell
// ---------------------------------------------------------------------------

function EditableCell({
  value,
  onSave,
  type = "text",
  placeholder = "",
}: {
  value: string;
  onSave: (val: string) => void;
  type?: string;
  placeholder?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const commit = () => {
    setEditing(false);
    if (draft !== value) onSave(draft);
  };

  if (!editing) {
    return (
      <span
        className="cursor-pointer hover:bg-slate-100 rounded px-1 py-0.5 min-w-[4rem] inline-block"
        onClick={() => {
          setDraft(value);
          setEditing(true);
        }}
      >
        {value || <span className="text-slate-400">{placeholder}</span>}
      </span>
    );
  }

  return (
    <input
      ref={inputRef}
      type={type}
      value={draft}
      className="border border-slate-300 rounded px-1 py-0.5 text-sm w-full"
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") { setEditing(false); setDraft(value); }
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Status select (inline)
// ---------------------------------------------------------------------------

function StatusSelect({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  return (
    <select
      value={value}
      className="text-xs border border-slate-200 rounded px-1 py-0.5 bg-white"
      onChange={(e) => onSave(e.target.value)}
    >
      {STATUS_OPTIONS.map((s) => (
        <option key={s} value={s}>{s.replace("_", " ")}</option>
      ))}
    </select>
  );
}

// ---------------------------------------------------------------------------
// New task row (inline form at bottom of a group)
// ---------------------------------------------------------------------------

function NewTaskRow({
  courseId,
  courseName,
  onSave,
  onCancel,
}: {
  courseId: string;
  courseName: string;
  onSave: (data: { name: string; due_at: string | null; user_estimated_minutes: number | null }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [hours, setHours] = useState("");
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => { nameRef.current?.focus(); }, []);

  const handleSave = () => {
    if (!name.trim()) return;
    onSave({
      name: name.trim(),
      due_at: dueAt || null,
      user_estimated_minutes: fromHours(hours),
    });
  };

  return (
    <tr className="bg-green-50">
      <td className="px-3 py-2">
        <input
          ref={nameRef}
          type="text"
          placeholder="Task name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="border border-slate-300 rounded px-2 py-1 text-sm w-full"
          onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") onCancel(); }}
        />
      </td>
      <td className="px-3 py-2 text-sm text-slate-500">{courseName}</td>
      <td className="px-3 py-2">
        <input
          type="date"
          value={dueAt}
          onChange={(e) => setDueAt(e.target.value)}
          className="border border-slate-300 rounded px-1 py-0.5 text-sm"
        />
      </td>
      <td className="px-3 py-2">
        <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-green-100 text-green-700">manual</span>
      </td>
      <td className="px-3 py-2">
        <input
          type="number"
          min="0"
          step="0.5"
          placeholder="hrs"
          value={hours}
          onChange={(e) => setHours(e.target.value)}
          className="border border-slate-300 rounded px-1 py-0.5 text-sm w-20"
        />
      </td>
      <td className="px-3 py-2 text-xs text-slate-400">pending</td>
      <td className="px-3 py-2">
        <div className="flex gap-2">
          <button
            onClick={handleSave}
            className="text-xs text-green-700 font-medium hover:underline"
          >
            Save
          </button>
          <button onClick={onCancel} className="text-xs text-slate-400 hover:underline">Cancel</button>
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function TasksPage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  const [groups, setGroups] = useState<CourseGroup[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [addingTo, setAddingTo] = useState<string | null>(null); // course_name adding to
  const [savingId, setSavingId] = useState<string | null>(null);

  const userId = session?.user?.id;

  useEffect(() => {
    if (status === "unauthenticated") router.push("/login");
  }, [status, router]);

  useEffect(() => {
    if (!userId) return;
    Promise.all([listTasks(userId), getSetupCourses(userId)]).then(([taskData, courseData]) => {
      setGroups(taskData.groups);
      setCourses(courseData.courses.filter((c) => c.internal_id !== null));
      setIsLoading(false);
    });
  }, [userId]);

  const reload = async () => {
    if (!userId) return;
    try {
      const data = await listTasks(userId);
      setGroups(data.groups);
    } catch {
      // ignore reload errors — UI will sync on next user action
    }
  };

  const handleUpdate = async (taskId: string, field: string, raw: string) => {
    if (!userId) return;
    setSavingId(taskId);
    try {
      let payload: Record<string, unknown> = {};
      if (field === "name") payload.name = raw;
      if (field === "due_at") payload.due_at = raw; // empty string = clear
      if (field === "hours") payload.user_estimated_minutes = fromHours(raw);
      if (field === "done") payload.completed_minutes = fromHours(raw);
      if (field === "status") payload.status = raw;
      await updateTask(userId, taskId, payload as Parameters<typeof updateTask>[2]);
      await reload();
    } finally {
      setSavingId(null);
    }
  };

  const handleDelete = async (taskId: string) => {
    if (!userId) return;
    try {
      await deleteTask(userId, taskId);
    } catch {
      // 404 = already deleted; reload will clear stale row
    }
    await reload();
  };

  const handleCreate = async (
    courseId: string,
    data: { name: string; due_at: string | null; user_estimated_minutes: number | null }
  ) => {
    if (!userId) return;
    await createTask(userId, { course_id: courseId, ...data });
    setAddingTo(null);
    await reload();
  };

  if (status === "loading" || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <p className="text-slate-500">Loading tasks...</p>
      </div>
    );
  }

  if (!session) return null;

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="border-b bg-white">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-slate-500 hover:text-slate-700 text-sm">← Dashboard</Link>
            <h1 className="font-semibold text-lg">Tasks</h1>
          </div>
          <span className="text-sm text-slate-500">{groups.reduce((n, g) => n + g.tasks.length, 0)} tasks total</span>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6 space-y-8">
        {groups.length === 0 && (
          <div className="text-center py-16 text-slate-400">
            <p className="text-lg mb-2">No tasks yet.</p>
            <Link href="/setup" className="text-blue-600 hover:underline text-sm">Complete course setup →</Link>
          </div>
        )}

        {groups.map((group) => {
          // Find the internal course ID for this group (needed for add-task)
          const course = courses.find((c) => c.name === group.course_name);
          const courseId = course?.internal_id ?? null;

          return (
            <section key={group.course_name}>
              {/* Course header */}
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-semibold text-slate-800 text-base">{group.course_name}</h2>
                <span className="text-xs text-slate-400">{group.tasks.length} tasks</span>
              </div>

              <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium text-slate-600 w-[35%]">Name</th>
                      <th className="text-left px-3 py-2 font-medium text-slate-600 w-[12%]">Course</th>
                      <th className="text-left px-3 py-2 font-medium text-slate-600 w-[12%]">Due</th>
                      <th className="text-left px-3 py-2 font-medium text-slate-600 w-[10%]">Source</th>
                      <th className="text-left px-3 py-2 font-medium text-slate-600 w-[10%]">Est. hrs</th>
                      <th className="text-left px-3 py-2 font-medium text-slate-600 w-[10%]">Done hrs</th>
                      <th className="text-left px-3 py-2 font-medium text-slate-600 w-[10%]">Remaining</th>
                      <th className="text-left px-3 py-2 font-medium text-slate-600 w-[10%]">Status</th>
                      <th className="px-3 py-2 w-[9%]"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {group.tasks.map((task) => (
                      <tr
                        key={task.id}
                        className={`hover:bg-slate-50 transition-colors ${savingId === task.id ? "opacity-60" : ""}`}
                      >
                        {/* Name */}
                        <td className="px-3 py-2">
                          <EditableCell
                            value={task.name}
                            placeholder="Task name"
                            onSave={(v) => handleUpdate(task.id, "name", v)}
                          />
                        </td>

                        {/* Course (read-only) */}
                        <td className="px-3 py-2 text-slate-500 text-xs">{task.course_name}</td>

                        {/* Due date */}
                        <td className="px-3 py-2">
                          <EditableCell
                            value={formatDate(task.due_at)}
                            type="date"
                            placeholder="—"
                            onSave={(v) => handleUpdate(task.id, "due_at", v)}
                          />
                        </td>

                        {/* Source badge */}
                        <td className="px-3 py-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SOURCE_BADGE[task.source] ?? ""}`}>
                            {task.source}
                          </span>
                        </td>

                        {/* Est. hours */}
                        <td className="px-3 py-2">
                          <EditableCell
                            value={toHours(task.user_estimated_minutes ?? task.estimated_minutes)}
                            type="number"
                            placeholder="—"
                            onSave={(v) => handleUpdate(task.id, "hours", v)}
                          />
                        </td>

                        {/* Done hours */}
                        <td className="px-3 py-2">
                          <EditableCell
                            value={toHours(task.completed_minutes)}
                            type="number"
                            placeholder="0"
                            onSave={(v) => handleUpdate(task.id, "done", v)}
                          />
                        </td>

                        {/* Remaining (read-only) */}
                        <td className="px-3 py-2 text-sm">
                          {task.remaining_minutes != null ? (
                            <span className={task.remaining_minutes === 0 ? "text-green-600 font-medium" : "text-slate-600"}>
                              {toHours(task.remaining_minutes) || "0"} hrs
                            </span>
                          ) : (
                            <span className="text-slate-300">—</span>
                          )}
                        </td>

                        {/* Status */}
                        <td className="px-3 py-2">
                          <StatusSelect
                            value={task.status}
                            onSave={(v) => handleUpdate(task.id, "status", v)}
                          />
                        </td>

                        {/* Delete */}
                        <td className="px-3 py-2 text-right">
                          <button
                            onClick={() => handleDelete(task.id)}
                            className="px-2 py-1 text-xs rounded text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors border border-transparent hover:border-red-200"
                            title="Delete task"
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}

                    {/* New task row */}
                    {addingTo === group.course_name && courseId && (
                      <NewTaskRow
                        courseId={courseId}
                        courseName={group.course_name}
                        onSave={(data) => handleCreate(courseId, data)}
                        onCancel={() => setAddingTo(null)}
                      />
                    )}
                  </tbody>
                </table>

                {/* Add task button */}
                {courseId && addingTo !== group.course_name && (
                  <div className="px-3 py-2 border-t border-slate-100">
                    <button
                      onClick={() => setAddingTo(group.course_name)}
                      className="text-xs text-slate-400 hover:text-slate-600 hover:underline"
                    >
                      + Add task
                    </button>
                  </div>
                )}
              </div>
            </section>
          );
        })}
      </main>
    </div>
  );
}

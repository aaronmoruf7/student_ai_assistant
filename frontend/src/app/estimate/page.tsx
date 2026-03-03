"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";

import { getEstimateGroups, applyEstimates } from "@/lib/api";

type TaskType = {
  type_label: string;
  representative: string;
  count: number;
  examples: string[];
};

type CourseGroup = {
  course_id: string;
  course_name: string;
  types: TaskType[];
};

// hours input keyed by "course_id::type_label"
type HoursMap = Record<string, string>;

export default function EstimatePage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  const [courses, setCourses] = useState<CourseGroup[]>([]);
  const [hours, setHours] = useState<HoursMap>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isClustering, setIsClustering] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [applied, setApplied] = useState<number | null>(null);

  const userId = session?.user?.id;

  useEffect(() => {
    if (status === "unauthenticated") router.push("/login");
  }, [status, router]);

  useEffect(() => {
    if (!userId) return;
    setIsClustering(true);
    getEstimateGroups(userId)
      .then((data) => setCourses(data.courses))
      .finally(() => {
        setIsLoading(false);
        setIsClustering(false);
      });
  }, [userId]);

  const key = (courseId: string, typeLabel: string) =>
    `${courseId}::${typeLabel}`;

  const handleHoursChange = (courseId: string, typeLabel: string, val: string) => {
    setHours((prev) => ({ ...prev, [key(courseId, typeLabel)]: val }));
    setApplied(null);
  };

  const handleApply = async () => {
    if (!userId) return;

    const estimates: Array<{ course_id: string; type_label: string; minutes: number }> = [];

    for (const course of courses) {
      for (const type of course.types) {
        const raw = hours[key(course.course_id, type.type_label)] ?? "";
        const h = parseFloat(raw);
        if (!isNaN(h) && h > 0) {
          estimates.push({
            course_id: course.course_id,
            type_label: type.type_label,
            minutes: Math.round(h * 60),
          });
        }
      }
    }

    if (estimates.length === 0) return;

    setIsApplying(true);
    try {
      const result = await applyEstimates(userId, estimates);
      setApplied(result.tasks_updated);
    } finally {
      setIsApplying(false);
    }
  };

  const totalFilled = courses.reduce((n, course) =>
    n + course.types.filter((t) => {
      const raw = hours[key(course.course_id, t.type_label)] ?? "";
      return parseFloat(raw) > 0;
    }).length, 0
  );

  if (status === "loading" || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="text-center space-y-2">
          <p className="text-slate-600 font-medium">
            {isClustering ? "Grouping tasks by type..." : "Loading..."}
          </p>
          {isClustering && (
            <p className="text-slate-400 text-sm">This may take a moment on first visit.</p>
          )}
        </div>
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
            <Link href="/" className="text-slate-500 hover:text-slate-700 text-sm">
              ← Dashboard
            </Link>
            <h1 className="font-semibold text-lg">Estimate Workload</h1>
          </div>
          <p className="text-sm text-slate-500">
            How long does each type of task take you?
          </p>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6 max-w-3xl space-y-8">

        {courses.length === 0 && (
          <div className="text-center py-16 text-slate-400">
            <p className="text-lg mb-2">No tasks to estimate.</p>
            <Link href="/setup" className="text-blue-600 hover:underline text-sm">
              Complete course setup first →
            </Link>
          </div>
        )}

        {courses.map((course) => (
          <section key={course.course_id}>
            <h2 className="font-semibold text-slate-800 mb-3">{course.course_name}</h2>

            <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
              {course.types.map((type) => {
                const val = hours[key(course.course_id, type.type_label)] ?? "";
                return (
                  <div
                    key={type.type_label}
                    className="px-4 py-3 flex items-center gap-4"
                  >
                    {/* Type info */}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-slate-800 text-sm">
                        {type.type_label}
                        <span className="ml-2 text-xs font-normal text-slate-400">
                          {type.count} task{type.count !== 1 ? "s" : ""}
                        </span>
                      </p>
                      <p className="text-xs text-slate-400 truncate mt-0.5">
                        e.g. {type.examples.slice(0, 2).join(", ")}
                      </p>
                    </div>

                    {/* Hours input */}
                    <div className="flex items-center gap-2 shrink-0">
                      <input
                        type="number"
                        min="0"
                        step="0.25"
                        placeholder="—"
                        value={val}
                        onChange={(e) =>
                          handleHoursChange(course.course_id, type.type_label, e.target.value)
                        }
                        className="w-20 border border-slate-300 rounded px-2 py-1.5 text-sm text-right focus:outline-none focus:ring-2 focus:ring-blue-300"
                      />
                      <span className="text-xs text-slate-400 w-6">hrs</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        ))}

        {/* Apply button */}
        {courses.length > 0 && (
          <div className="flex items-center justify-between pt-2">
            <div>
              {applied !== null && (
                <p className="text-sm text-green-600 font-medium">
                  ✓ Updated {applied} tasks.{" "}
                  <Link href="/tasks" className="underline">
                    Review in Tasks →
                  </Link>
                </p>
              )}
            </div>
            <button
              onClick={handleApply}
              disabled={isApplying || totalFilled === 0}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {isApplying ? "Applying..." : "Apply estimates"}
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

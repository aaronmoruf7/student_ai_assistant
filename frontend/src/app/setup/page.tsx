"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import {
  connectCanvas,
  getSetupCourses,
  selectCourses,
  createManualCourse,
  getUndatedClusters,
  confirmUndated,
  extractTasksFromContent,
  confirmExtractedTasks,
} from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

type Course = {
  canvas_course_id: number | null;
  name: string;
  code: string | null;
  term: string | null;
  selected: boolean;
  setup_complete: boolean;
  internal_id: string | null;
  manual?: boolean; // true if user-created
};

type ExtractedTask = {
  title: string;
  type: string;
  due_date: string | null;
  confidence: number;
};

type UndatedCluster = {
  type_label: string;
  representative: string;
  count: number;
  examples: string[];
  assignment_ids: number[];
  course_name: string;
  canvas_course_id: number;
};

const STEPS = ["Select Courses", "Add Content", "Undated Tasks", "Save"];

// ─── Component ───────────────────────────────────────────────────────────────

export default function SetupPage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  const [step, setStep] = useState(0);
  const [hasCanvas, setHasCanvas] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 0: Canvas connect
  const [canvasUrl, setCanvasUrl] = useState("");
  const [canvasToken, setCanvasToken] = useState("");

  // Step 1: Course selection
  const [courses, setCourses] = useState<Course[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number | string>>(new Set());
  const [manualCourseForm, setManualCourseForm] = useState({ name: "", code: "", term: "" });

  // Step 2: Per-course content (remember data for each course separately)
  const [selectedCourses, setSelectedCourses] = useState<Course[]>([]);
  const [courseStep, setCourseStep] = useState(0);
  const [courseContents, setCourseContents] = useState<Record<string, string>>({}); // courseKey → pasted content
  const [courseExtractedTasks, setCourseExtractedTasks] = useState<Record<string, ExtractedTask[]>>({}); // courseKey → tasks
  const [courseConfirmedIndices, setCourseConfirmedIndices] = useState<Record<string, Set<number>>>({}); // courseKey → confirmed indices
  const [extracting, setExtracting] = useState(false);
  const [coursesWithChanges, setCoursesWithChanges] = useState<Set<string>>(new Set());

  // Step 3: Undated assignments
  const [undatedClusters, setUndatedClusters] = useState<UndatedCluster[]>([]);
  const [confirmedLabels, setConfirmedLabels] = useState<Set<string>>(new Set());
  const [undatedSearched, setUndatedSearched] = useState(false);

  const userId = session?.user?.id;

  // ── localStorage persistence ──────────────────────────────────────────

  const STORAGE_KEY = "setup_progress";

  function saveProgress() {
    // Convert per-course Sets to arrays for JSON serialization
    const courseConfirmedArrays: Record<string, number[]> = {};
    for (const [key, set] of Object.entries(courseConfirmedIndices)) {
      courseConfirmedArrays[key] = Array.from(set);
    }

    const state = {
      step,
      hasCanvas,
      courses,
      selectedIds: Array.from(selectedIds),
      selectedCourses,
      courseStep,
      courseContents,
      courseExtractedTasks,
      courseConfirmedIndices: courseConfirmedArrays,
      undatedClusters,
      confirmedLabels: Array.from(confirmedLabels),
      coursesWithChanges: Array.from(coursesWithChanges),
      undatedSearched,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function restoreProgress() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return;
    try {
      const state = JSON.parse(saved);
      setStep(state.step);
      setHasCanvas(state.hasCanvas);
      setCourses(state.courses);
      setSelectedIds(new Set(state.selectedIds));
      setSelectedCourses(state.selectedCourses);
      setCourseStep(state.courseStep || 0); // Reset to 0 when restoring
      setCourseContents(state.courseContents || {});
      setCourseExtractedTasks(state.courseExtractedTasks || {});

      // Convert arrays back to Sets for confirmed indices
      const courseConfirmedSets: Record<string, Set<number>> = {};
      if (state.courseConfirmedIndices) {
        for (const [key, arr] of Object.entries(state.courseConfirmedIndices as Record<string, number[]>)) {
          courseConfirmedSets[key] = new Set(arr);
        }
      }
      setCourseConfirmedIndices(courseConfirmedSets);

      setUndatedClusters(state.undatedClusters);
      setConfirmedLabels(new Set(state.confirmedLabels));
      setCoursesWithChanges(new Set(state.coursesWithChanges));
      setUndatedSearched(state.undatedSearched);
    } catch {
      // Ignore parse errors
    }
  }

  useEffect(() => {
    if (status === "unauthenticated") router.push("/login");
  }, [status, router]);

  useEffect(() => {
    if (!session) return;
    const connected = session.user.hasCanvas;
    setHasCanvas(connected);
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      restoreProgress();
      // After restoring, if they were on step 5 (completion), start them at step 1 for editing
      const state = JSON.parse(saved);
      if (state.step === 5) {
        setStep(1);
      }
    } else if (connected) {
      setStep(1);
      loadCourses();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  useEffect(() => {
    if (step >= 1 && userId) {
      saveProgress();
    }
  }, [step, courses, selectedIds, selectedCourses, courseStep, courseContents, courseExtractedTasks, courseConfirmedIndices, undatedClusters, confirmedLabels, coursesWithChanges, undatedSearched, userId]);

  // ── Loaders ──────────────────────────────────────────────────────────────

  async function loadCourses() {
    if (!userId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await getSetupCourses(userId);
      setCourses(data.courses);
      const preSelected = new Set(
        data.courses.filter((c) => c.selected).map((c) => c.canvas_course_id)
      );
      setSelectedIds(preSelected);
    } catch {
      setError("Failed to load courses. Check your Canvas connection.");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadUndated() {
    if (!userId) return;
    // Only load if we haven't searched yet OR if courses with changes are selected
    const hasChangedCourses = selectedCourses.some(c => coursesWithChanges.has(getCourseKey(c)));
    if (undatedSearched && !hasChangedCourses) {
      // Use cached results
      setStep(3);
      return;
    }

    setStep(3);
    setIsLoading(true);
    setError(null);
    try {
      const data = await getUndatedClusters(userId);
      setUndatedClusters(data.clusters);
      setConfirmedLabels(new Set(data.clusters.map((c) => c.type_label)));
      setUndatedSearched(true);
    } catch {
      setError("Failed to load undated assignments.");
    } finally {
      setIsLoading(false);
    }
  }

  // ── Handlers ─────────────────────────────────────────────────────────────

  function getCourseKey(course: Course): string {
    return course.manual
      ? `manual_${course.name}`
      : `canvas_${course.canvas_course_id}`;
  }

  async function handleConnectCanvas() {
    if (!userId || !canvasUrl || !canvasToken) return;
    setIsLoading(true);
    setError(null);
    try {
      await connectCanvas(userId, canvasUrl, canvasToken);
      setHasCanvas(true);
      setStep(1);
      await loadCourses();
    } catch {
      setError("Could not connect to Canvas. Check your URL and token.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleAddManualCourse() {
    if (!userId || !manualCourseForm.name.trim()) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await createManualCourse(
        userId,
        manualCourseForm.name,
        manualCourseForm.code,
        manualCourseForm.term
      );
      const newCourse: Course = {
        canvas_course_id: response.canvas_course_id,  // Use the negative ID from backend
        name: manualCourseForm.name,
        code: manualCourseForm.code || null,
        term: manualCourseForm.term || null,
        selected: false,
        setup_complete: false,
        internal_id: response.id,
        manual: true,
      };
      setCourses([...courses, newCourse]);
      setManualCourseForm({ name: "", code: "", term: "" });
    } catch {
      setError("Failed to add course. Try again.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSelectCourses() {
    if (!userId || selectedIds.size === 0) return;
    setIsLoading(true);
    setError(null);
    try {
      // Separate Canvas and manual courses
      const canvasIds = Array.from(selectedIds).filter((id) => typeof id === "number") as number[];
      if (canvasIds.length > 0) {
        await selectCourses(userId, canvasIds);
      }

      const selected = courses.filter((c) => {
        if (c.manual) return selectedIds.has(`manual_${c.name}`);
        return selectedIds.has(c.canvas_course_id);
      });
      setSelectedCourses(selected);

      // Always start at course 0 when entering step 2
      // (per-course content is preserved in courseContents)
      setCourseStep(0);

      setStep(2);
    } catch {
      setError("Failed to save courses. Try again.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleExtract() {
    const course = selectedCourses[courseStep];
    const courseKey = getCourseKey(course);
    const content = courseContents[courseKey] || "";
    if (!userId || !content.trim()) return;
    setExtracting(true);
    setError(null);
    try {
      const courseId = course.canvas_course_id || 0;
      const data = await extractTasksFromContent(userId, courseId, content);
      // Save extracted tasks per-course
      setCourseExtractedTasks({
        ...courseExtractedTasks,
        [courseKey]: data.extracted,
      });
      // Mark all extracted tasks as confirmed by default
      setCourseConfirmedIndices({
        ...courseConfirmedIndices,
        [courseKey]: new Set(data.extracted.map((_, i) => i)),
      });
      // Mark this course as changed
      setCoursesWithChanges(new Set([...coursesWithChanges, courseKey]));
    } catch {
      setError("Extraction failed. Try again.");
    } finally {
      setExtracting(false);
    }
  }

  async function handleSaveCourse() {
    if (!userId) return;
    const course = selectedCourses[courseStep];
    const courseKey = getCourseKey(course);
    const tasks = courseExtractedTasks[courseKey] || [];
    const confirmed = courseConfirmedIndices[courseKey] || new Set();
    const tasksToSave = tasks.filter((_, i) => confirmed.has(i));
    setIsLoading(true);
    setError(null);
    try {
      if (tasksToSave.length > 0) {
        const courseId = course.canvas_course_id!;
        await confirmExtractedTasks(userId, courseId, tasksToSave);
      }
      advanceCourseStep();
    } catch {
      setError("Failed to save tasks.");
    } finally {
      setIsLoading(false);
    }
  }

  function advanceCourseStep() {
    const next = courseStep + 1;
    if (next >= selectedCourses.length) {
      loadUndated();
    } else {
      // Just move to next course — per-course data is preserved
      setCourseStep(next);
    }
  }

  function goBackCourseStep() {
    if (courseStep > 0) {
      // Just move to previous course — per-course data is preserved
      setCourseStep(courseStep - 1);
    }
  }

  async function handleConfirmUndated() {
    if (!userId) return;
    setIsLoading(true);
    setError(null);
    try {
      const confirmed: Record<string, number[]> = {};
      for (const cluster of undatedClusters) {
        if (!confirmedLabels.has(cluster.type_label)) continue;
        const key = String(cluster.canvas_course_id);
        if (!confirmed[key]) confirmed[key] = [];
        confirmed[key].push(...cluster.assignment_ids);
      }
      await confirmUndated(userId, confirmed);
      setStep(4);
    } catch {
      setError("Failed to confirm assignments.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleFinalSave() {
    if (!userId) return;
    setIsSaving(true);
    setError(null);
    try {
      // All tasks have already been saved during the flow
      // Keep localStorage so user can come back and edit anytime
      // (don't clear it — they might want to make changes later)
      setStep(5); // Success state
    } catch {
      setError("Failed to finalize setup.");
    } finally {
      setIsSaving(false);
    }
  }

  // ── Render guards ─────────────────────────────────────────────────────────

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <p className="text-slate-500">Loading...</p>
      </div>
    );
  }

  if (!session) return null;

  const showStepIndicator = step >= 1 && step <= 4;
  const currentStepIndex = step - 1;

  // ── UI ────────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center py-12 px-4">
      <div className="w-full max-w-xl space-y-6">

        {/* Header */}
        <div className="text-center">
          <div className="text-4xl mb-2">📚</div>
          <h1 className="text-2xl font-semibold text-slate-800">Your course setup</h1>
          <p className="text-slate-500 mt-1 text-sm">
            Configure your courses anytime. Changes auto-save.
          </p>
        </div>

        {/* Step indicator */}
        {showStepIndicator && (
          <div className="flex items-center justify-center gap-2">
            {STEPS.map((label, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className="flex items-center gap-1.5">
                  <div
                    className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                      i < currentStepIndex
                        ? "bg-green-500 text-white"
                        : i === currentStepIndex
                        ? "bg-slate-800 text-white"
                        : "bg-slate-200 text-slate-400"
                    }`}
                  >
                    {i < currentStepIndex ? "✓" : i + 1}
                  </div>
                  <span
                    className={`text-xs ${
                      i === currentStepIndex ? "text-slate-800 font-medium" : "text-slate-400"
                    }`}
                  >
                    {label}
                  </span>
                </div>
                {i < STEPS.length - 1 && <div className="w-8 h-px bg-slate-200" />}
              </div>
            ))}
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
            {error}
          </div>
        )}

        {/* ── Step 0: Connect Canvas ── */}
        {step === 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Connect Canvas</CardTitle>
              <CardDescription>
                Enter your Canvas domain and a personal access token to import your courses.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Canvas URL</label>
                <Input
                  placeholder="canvas.youruniversity.edu"
                  value={canvasUrl}
                  onChange={(e) => setCanvasUrl(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Access Token</label>
                <Input
                  type="password"
                  placeholder="Paste your Canvas personal access token"
                  value={canvasToken}
                  onChange={(e) => setCanvasToken(e.target.value)}
                />
                <p className="text-xs text-slate-400">
                  Canvas → Account → Settings → Approved Integrations → New Access Token
                </p>
              </div>
              <Button
                onClick={handleConnectCanvas}
                disabled={!canvasUrl || !canvasToken || isLoading}
                className="w-full"
              >
                {isLoading ? "Connecting..." : "Connect Canvas"}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* ── Step 1: Select Courses ── */}
        {step === 1 && (
          <Card>
            <CardHeader>
              <CardTitle>Select your courses</CardTitle>
              <CardDescription>
                Choose Canvas courses or add custom ones manually.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Canvas courses */}
              {isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="animate-pulse h-14 bg-slate-100 rounded-lg" />
                  ))}
                </div>
              ) : courses.filter(c => !c.manual).length === 0 ? (
                <p className="text-sm text-slate-500">No Canvas courses found.</p>
              ) : (
                <div className="space-y-2">
                  {courses.filter(c => !c.manual).map((c) => (
                    <label
                      key={c.canvas_course_id}
                      className="flex items-center gap-3 p-3 rounded-lg border border-slate-200 hover:bg-slate-50 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        className="w-4 h-4 rounded"
                        checked={selectedIds.has(c.canvas_course_id!)}
                        onChange={(e) => {
                          const next = new Set(selectedIds);
                          if (e.target.checked) next.add(c.canvas_course_id!);
                          else next.delete(c.canvas_course_id!);
                          setSelectedIds(next);
                        }}
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-800 truncate">{c.name}</p>
                        <p className="text-xs text-slate-400">
                          {c.code}
                          {c.term ? ` · ${c.term}` : ""}
                        </p>
                      </div>
                    </label>
                  ))}
                </div>
              )}

              {/* Manual courses */}
              {courses.filter(c => c.manual).length > 0 && (
                <>
                  <div className="border-t pt-4">
                    <p className="text-xs font-medium text-slate-500 mb-2">Your custom courses</p>
                    <div className="space-y-2">
                      {courses.filter(c => c.manual).map((c) => (
                        <label
                          key={`manual_${c.name}`}
                          className="flex items-center gap-3 p-3 rounded-lg border border-slate-200 hover:bg-slate-50 cursor-pointer bg-blue-50"
                        >
                          <input
                            type="checkbox"
                            className="w-4 h-4 rounded"
                            checked={selectedIds.has(`manual_${c.name}`)}
                            onChange={(e) => {
                              const next = new Set(selectedIds);
                              if (e.target.checked) next.add(`manual_${c.name}`);
                              else next.delete(`manual_${c.name}`);
                              setSelectedIds(next);
                            }}
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-slate-800 truncate">{c.name}</p>
                            <p className="text-xs text-slate-400">
                              {c.code}
                              {c.term ? ` · ${c.term}` : ""}
                            </p>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>
                </>
              )}

              {/* Add manual course form */}
              <div className="border-t pt-4 space-y-3">
                <p className="text-sm font-medium text-slate-700">Add a custom course</p>
                <div className="space-y-2">
                  <Input
                    placeholder="Course name"
                    value={manualCourseForm.name}
                    onChange={(e) =>
                      setManualCourseForm({ ...manualCourseForm, name: e.target.value })
                    }
                  />
                  <Input
                    placeholder="Code (optional)"
                    value={manualCourseForm.code}
                    onChange={(e) =>
                      setManualCourseForm({ ...manualCourseForm, code: e.target.value })
                    }
                  />
                  <Input
                    placeholder="Term (optional)"
                    value={manualCourseForm.term}
                    onChange={(e) =>
                      setManualCourseForm({ ...manualCourseForm, term: e.target.value })
                    }
                  />
                  <Button
                    variant="outline"
                    onClick={handleAddManualCourse}
                    disabled={!manualCourseForm.name.trim()}
                    className="w-full"
                  >
                    Add course
                  </Button>
                </div>
              </div>

              <Button
                onClick={handleSelectCourses}
                disabled={selectedIds.size === 0 || isLoading}
                className="w-full"
              >
                {isLoading
                  ? "Saving..."
                  : `Continue with ${selectedIds.size} course${selectedIds.size !== 1 ? "s" : ""}`}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* ── Step 2: Per-course supplemental content ── */}
        {step === 2 && selectedCourses.length > 0 && (
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <CardTitle>{selectedCourses[courseStep].name}</CardTitle>
                  <CardDescription className="mt-1">
                    Paste any extra content — syllabus, schedule, assignment list — so we can
                    find all deadlines.
                  </CardDescription>
                </div>
                <span className="text-xs text-slate-400 shrink-0 mt-1">
                  {courseStep + 1} / {selectedCourses.length}
                </span>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {(() => {
                const courseKey = getCourseKey(selectedCourses[courseStep]);
                const content = courseContents[courseKey] || "";
                const tasks = courseExtractedTasks[courseKey] || [];
                return tasks.length === 0 ? (
                  <>
                    <textarea
                      className="w-full h-44 text-sm border border-slate-200 rounded-lg p-3 resize-none focus:outline-none focus:ring-2 focus:ring-slate-300 placeholder:text-slate-400"
                      placeholder="Paste your syllabus, course schedule, or assignment list here..."
                      value={content}
                      onChange={(e) =>
                        setCourseContents({ ...courseContents, [courseKey]: e.target.value })
                      }
                    />
                    <div className="flex gap-2">
                      <Button
                        onClick={handleExtract}
                        disabled={!content.trim() || extracting}
                        className="flex-1"
                      >
                        {extracting ? "Extracting..." : "Extract tasks"}
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => {
                          advanceCourseStep();
                        }}
                        disabled={extracting}
                      >
                        Skip
                      </Button>
                      {courseStep > 0 && (
                        <Button variant="outline" onClick={goBackCourseStep} disabled={extracting}>
                          ← Back
                        </Button>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-sm text-slate-600">
                      Found{" "}
                      <span className="font-medium">{tasks.length} tasks</span>. Uncheck
                      any that aren&apos;t real assignments.
                    </p>
                  <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                    {tasks.map((task, i) => {
                      const confirmed = courseConfirmedIndices[courseKey] || new Set();
                      return (
                        <label
                          key={i}
                          className="flex items-start gap-3 p-3 rounded-lg border border-slate-200 hover:bg-slate-50 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            className="w-4 h-4 rounded mt-0.5 shrink-0"
                            checked={confirmed.has(i)}
                            onChange={(e) => {
                              const next = new Set(confirmed);
                              if (e.target.checked) next.add(i);
                              else next.delete(i);
                              setCourseConfirmedIndices({
                                ...courseConfirmedIndices,
                                [courseKey]: next,
                              });
                            }}
                          />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-slate-800">{task.title}</p>
                            <p className="text-xs text-slate-400">
                              {task.type}
                              {task.due_date ? ` · Due ${task.due_date}` : ""}
                            </p>
                          </div>
                          <ConfidenceBadge confidence={task.confidence} />
                        </label>
                      );
                    })}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      onClick={handleSaveCourse}
                      disabled={isLoading}
                      className="flex-1"
                    >
                      {isLoading
                        ? "Saving..."
                        : `Save ${(courseConfirmedIndices[courseKey] || new Set()).size} task${(courseConfirmedIndices[courseKey] || new Set()).size !== 1 ? "s" : ""}`}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setCourseExtractedTasks({
                          ...courseExtractedTasks,
                          [courseKey]: [],
                        });
                      }}
                    >
                      Re-paste
                    </Button>
                    {courseStep > 0 && (
                      <Button variant="outline" onClick={goBackCourseStep}>
                        ← Back
                      </Button>
                    )}
                  </div>
                </>
              );
              })()}
            </CardContent>
          </Card>
        )}

        {/* ── Step 3: Undated assignments ── */}
        {step === 3 && (
          <Card>
            <CardHeader>
              <CardTitle>Undated assignments</CardTitle>
              <CardDescription>
                Canvas found these assignment types without due dates. Check the ones that are
                real tasks.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="animate-pulse h-14 bg-slate-100 rounded-lg" />
                  ))}
                </div>
              ) : undatedClusters.length === 0 ? (
                <div className="space-y-4">
                  <p className="text-sm text-slate-500">
                    No undated assignments found — you&apos;re all set!
                  </p>
                  <Button onClick={() => setStep(4)} className="w-full">
                    Continue to save
                  </Button>
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    {undatedClusters.map((cluster) => (
                      <label
                        key={`${cluster.canvas_course_id}-${cluster.type_label}`}
                        className="flex items-start gap-3 p-3 rounded-lg border border-slate-200 hover:bg-slate-50 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          className="w-4 h-4 rounded mt-0.5 shrink-0"
                          checked={confirmedLabels.has(cluster.type_label)}
                          onChange={(e) => {
                            const next = new Set(confirmedLabels);
                            if (e.target.checked) next.add(cluster.type_label);
                            else next.delete(cluster.type_label);
                            setConfirmedLabels(next);
                          }}
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-slate-800">
                            {cluster.type_label}
                          </p>
                          <p className="text-xs text-slate-400">
                            {cluster.course_name} · {cluster.count} assignment
                            {cluster.count !== 1 ? "s" : ""} · e.g. {cluster.representative}
                          </p>
                        </div>
                        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 shrink-0">
                          {cluster.count}
                        </span>
                      </label>
                    ))}
                  </div>
                  <Button
                    onClick={handleConfirmUndated}
                    disabled={isLoading}
                    className="w-full"
                  >
                    {isLoading ? "Saving..." : "Confirm & continue"}
                  </Button>
                </>
              )}
            </CardContent>
          </Card>
        )}

        {/* ── Step 4: Final Save ── */}
        {step === 4 && (
          <Card>
            <CardHeader>
              <CardTitle>Review and save</CardTitle>
              <CardDescription>
                All your course data is ready. Click save to finalize your setup.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="bg-slate-50 p-4 rounded-lg space-y-2">
                <p className="text-sm font-medium text-slate-700">
                  Courses selected: <span className="text-slate-900">{selectedCourses.length}</span>
                </p>
                <p className="text-sm font-medium text-slate-700">
                  Courses with content:{" "}
                  <span className="text-slate-900">{coursesWithChanges.size}</span>
                </p>
                <p className="text-xs text-slate-500 mt-3">
                  You can edit any course anytime by returning to this page.
                </p>
              </div>
              <Button onClick={handleFinalSave} disabled={isSaving} className="w-full">
                {isSaving ? "Saving..." : "✓ Save setup"}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* ── Step 5: Success ── */}
        {step === 5 && (
          <Card>
            <CardContent className="py-12 text-center space-y-4">
              <div className="text-5xl">✅</div>
              <h2 className="text-xl font-semibold text-slate-800">Setup complete!</h2>
              <p className="text-sm text-slate-500">
                Your courses are configured. You can edit anytime by returning here.
              </p>
              <div className="flex gap-2 mt-4">
                <Button
                  onClick={() => {
                    // Always go to step 1, but all data from localStorage is preserved
                    setStep(1);
                  }}
                  variant="outline"
                  className="flex-1"
                >
                  ← Edit setup
                </Button>
                <Button onClick={() => router.push("/")} className="flex-1">
                  Go to dashboard →
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

// ─── Confidence badge ─────────────────────────────────────────────────────────

function ConfidenceBadge({ confidence }: { confidence: number }) {
  if (confidence >= 0.8) {
    return (
      <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700 shrink-0">
        High
      </span>
    );
  }
  if (confidence >= 0.5) {
    return (
      <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-100 text-yellow-700 shrink-0">
        Med
      </span>
    );
  }
  return (
    <span className="text-xs px-1.5 py-0.5 rounded bg-red-100 text-red-700 shrink-0">
      Low
    </span>
  );
}

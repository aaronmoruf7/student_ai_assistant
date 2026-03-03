const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

// Workload
export async function getWorkloadRamps(userId: string, weeks = 4) {
  return fetchApi<{
    weeks: Array<{
      week_start: string;
      week_end: string;
      week_label: string;
      tasks_due: number;
      work_hours: number;
      available_hours: number;
      utilization: number;
      load_level: string;
      emoji: string;
      summary: string;
    }>;
  }>(`/workload/ramps?user_id=${userId}&weeks=${weeks}`);
}

// Tasks
export async function getTasks(userId: string) {
  return fetchApi<{
    tasks: Array<{
      id: string;
      name: string;
      course_name: string;
      due_at: string;
      points_possible: number;
      estimated_minutes: number;
      status: string;
    }>;
    count: number;
  }>(`/sync/tasks?user_id=${userId}`);
}

// Events
export async function getEvents(userId: string) {
  return fetchApi<{
    events: Array<{
      id: string;
      title: string;
      start: string;
      end: string;
      all_day: boolean;
      event_type: string;
    }>;
    count: number;
  }>(`/sync/events?user_id=${userId}`);
}

// Planner
export async function getWorkBlocks(userId: string, weeks = 1) {
  return fetchApi<{
    blocks: Array<{
      id: string;
      title: string;
      start: string;
      end: string;
      duration_minutes: number;
      status: string;
    }>;
    count: number;
  }>(`/planner/blocks?user_id=${userId}&weeks=${weeks}`);
}

export async function importPlanEvents(
  userId: string,
  events: Array<{ title: string; start: string; end: string; description?: string }>
) {
  return fetchApi<{ created: number; errors: Array<{ title: string; error: string }> }>(
    `/planner/import?user_id=${userId}`,
    { method: "POST", body: JSON.stringify({ events }) }
  );
}

export async function generatePlan(userId: string, weeks = 1, syncToCalendar = false) {
  return fetchApi<{
    blocks_created: number;
    blocks: Array<{
      task_name: string;
      course: string;
      start: string;
      end: string;
      duration_minutes: number;
    }>;
  }>(`/planner/generate?user_id=${userId}&weeks=${weeks}&sync_to_calendar=${syncToCalendar}`, {
    method: "POST",
  });
}

// Canvas connection
export async function connectCanvas(userId: string, canvasUrl: string, canvasToken: string) {
  return fetchApi(`/canvas/connect?user_id=${userId}`, {
    method: "POST",
    body: JSON.stringify({ canvas_url: canvasUrl, canvas_token: canvasToken }),
  });
}

// Setup flow
export async function getSetupCourses(userId: string) {
  return fetchApi<{
    courses: Array<{
      canvas_course_id: number;
      name: string;
      code: string | null;
      term: string | null;
      selected: boolean;
      setup_complete: boolean;
      internal_id: string | null;
    }>;
    count: number;
  }>(`/setup/courses?user_id=${userId}`);
}

export async function selectCourses(userId: string, canvasCourseIds: number[]) {
  return fetchApi<{ courses_created: number; tasks_imported: number; message: string }>(
    `/setup/courses/select?user_id=${userId}`,
    { method: "POST", body: JSON.stringify({ canvas_course_ids: canvasCourseIds }) }
  );
}

export async function createManualCourse(
  userId: string,
  name: string,
  code?: string,
  term?: string
) {
  return fetchApi<{
    id: string;
    canvas_course_id: number;
    name: string;
    code: string | null;
    term: string | null;
    message: string;
  }>(`/setup/courses/create-manual?user_id=${userId}`, {
    method: "POST",
    body: JSON.stringify({ name, code: code || null, term: term || null }),
  });
}

export async function getUndatedClusters(userId: string) {
  return fetchApi<{
    clusters: Array<{
      type_label: string;
      representative: string;
      count: number;
      examples: string[];
      assignment_ids: number[];
      course_name: string;
      canvas_course_id: number;
    }>;
    total_undated: number;
  }>(`/setup/undated?user_id=${userId}`);
}

export async function confirmUndated(userId: string, confirmed: Record<string, number[]>) {
  return fetchApi<{ tasks_created: number; message: string }>(
    `/setup/undated/confirm?user_id=${userId}`,
    { method: "POST", body: JSON.stringify({ confirmed }) }
  );
}

export async function extractTasksFromContent(
  userId: string,
  canvasCourseId: number,
  content: string
) {
  return fetchApi<{
    course_name: string;
    extracted: Array<{
      title: string;
      type: string;
      due_date: string | null;
      confidence: number;
    }>;
    count: number;
  }>(`/setup/courses/${canvasCourseId}/extract?user_id=${userId}`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function confirmExtractedTasks(
  userId: string,
  canvasCourseId: number,
  tasks: Array<{ title: string; type: string; due_date: string | null; confidence: number }>
) {
  return fetchApi<{
    tasks_created: number;
    course: string;
    setup_complete: boolean;
    message: string;
  }>(`/setup/courses/${canvasCourseId}/tasks/confirm?user_id=${userId}`, {
    method: "POST",
    body: JSON.stringify({ tasks }),
  });
}

// Chat
export type ChatMessage = { role: "user" | "assistant"; content: string };
export type ToolAction = { tool: string; label: string; success: boolean };

export async function sendChatMessage(
  userId: string,
  messages: ChatMessage[]
): Promise<{ reply: string; actions: ToolAction[]; onboarding_complete: boolean }> {
  return fetchApi(`/chat/message?user_id=${userId}`, {
    method: "POST",
    body: JSON.stringify({ messages }),
  });
}

export async function getChatStatus(userId: string) {
  return fetchApi<{ onboarding_complete: boolean; has_preferences: boolean }>(
    `/chat/status?user_id=${userId}`
  );
}

// Constraints
export type ConstraintData = {
  constraint_type: string;
  name: string;
  days_of_week?: number[] | null;
  start_time?: string | null;
  end_time?: string | null;
  max_minutes?: number | null;
  is_active: boolean;
};

export type ConstraintOut = ConstraintData & { id: string };

export async function listConstraints(userId: string) {
  return fetchApi<{ constraints: ConstraintOut[] }>(`/constraints?user_id=${userId}`);
}

export async function createConstraint(userId: string, data: ConstraintData) {
  return fetchApi<ConstraintOut>(`/constraints?user_id=${userId}`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateConstraint(userId: string, id: string, data: ConstraintData) {
  return fetchApi<ConstraintOut>(`/constraints/${id}?user_id=${userId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteConstraint(userId: string, id: string) {
  return fetchApi(`/constraints/${id}?user_id=${userId}`, { method: "DELETE" });
}

// Estimate
export async function getEstimateGroups(userId: string) {
  return fetchApi<{
    courses: Array<{
      course_id: string;
      course_name: string;
      types: Array<{
        type_label: string;
        representative: string;
        count: number;
        examples: string[];
      }>;
    }>;
  }>(`/estimate?user_id=${userId}`);
}

export async function applyEstimates(
  userId: string,
  estimates: Array<{ course_id: string; type_label: string; minutes: number }>
) {
  return fetchApi<{ tasks_updated: number; message: string }>(
    `/estimate?user_id=${userId}`,
    { method: "POST", body: JSON.stringify({ estimates }) }
  );
}

// Tasks CRUD
export async function listTasks(userId: string) {
  return fetchApi<{
    groups: Array<{
      course_name: string;
      tasks: Array<{
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
      }>;
    }>;
    total: number;
  }>(`/tasks?user_id=${userId}`);
}

export async function createTask(
  userId: string,
  data: {
    name: string;
    course_id: string;
    due_at?: string | null;
    user_estimated_minutes?: number | null;
  }
) {
  return fetchApi(`/tasks?user_id=${userId}`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateTask(
  userId: string,
  taskId: string,
  data: {
    name?: string;
    due_at?: string;
    user_estimated_minutes?: number | null;
    completed_minutes?: number | null;
    status?: string;
  }
) {
  return fetchApi(`/tasks/${taskId}?user_id=${userId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function deleteTask(userId: string, taskId: string) {
  return fetchApi(`/tasks/${taskId}?user_id=${userId}`, { method: "DELETE" });
}

// User profile
export async function getUserProfile(userId: string) {
  return fetchApi<{ name: string; email: string; ai_preferences: string | null }>(
    `/auth/profile?user_id=${userId}`
  );
}

export async function savePreferences(userId: string, ai_preferences: string) {
  return fetchApi<{ saved: boolean }>(`/auth/profile?user_id=${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ ai_preferences }),
  });
}

// Sync
export async function syncAll(userId: string) {
  return fetchApi<{
    canvas: { created?: number; updated?: number; error?: string };
    calendar: { created?: number; updated?: number; error?: string };
  }>(`/sync/all?user_id=${userId}`, {
    method: "POST",
  });
}

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

// Sync
export async function syncAll(userId: string) {
  return fetchApi<{
    canvas: { created?: number; updated?: number; error?: string };
    calendar: { created?: number; updated?: number; error?: string };
  }>(`/sync/all?user_id=${userId}`, {
    method: "POST",
  });
}

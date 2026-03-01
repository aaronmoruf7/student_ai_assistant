"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

interface Task {
  id: string;
  name: string;
  course_name: string;
  due_at: string;
  estimated_minutes: number;
  status: string;
}

interface TaskListProps {
  tasks: Task[];
  isLoading?: boolean;
}

export function TaskList({ tasks, isLoading }: TaskListProps) {
  if (isLoading) {
    return (
      <Card className="h-full">
        <CardHeader>
          <CardTitle className="text-lg">Upcoming Tasks</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="animate-pulse p-3 border rounded-lg">
                <div className="h-4 bg-slate-200 rounded w-3/4 mb-2"></div>
                <div className="h-3 bg-slate-200 rounded w-1/2"></div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-lg flex items-center justify-between">
          Upcoming Tasks
          <Badge variant="secondary">{tasks.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[300px] pr-4">
          <div className="space-y-3">
            {tasks.length === 0 ? (
              <p className="text-sm text-slate-500 text-center py-8">
                No upcoming tasks
              </p>
            ) : (
              tasks.slice(0, 10).map((task) => (
                <TaskItem key={task.id} task={task} />
              ))
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function TaskItem({ task }: { task: Task }) {
  const dueDate = new Date(task.due_at);
  const now = new Date();
  const daysUntilDue = Math.ceil(
    (dueDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)
  );

  const urgencyColor =
    daysUntilDue <= 1
      ? "border-red-200 bg-red-50"
      : daysUntilDue <= 3
      ? "border-yellow-200 bg-yellow-50"
      : "border-slate-200";

  return (
    <div className={`p-3 border rounded-lg ${urgencyColor}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm truncate">{task.name}</p>
          <p className="text-xs text-slate-500 truncate">{task.course_name}</p>
        </div>
        <Badge
          variant={daysUntilDue <= 1 ? "destructive" : "outline"}
          className="shrink-0 text-xs"
        >
          {daysUntilDue <= 0
            ? "Due today"
            : daysUntilDue === 1
            ? "Tomorrow"
            : `${daysUntilDue}d`}
        </Badge>
      </div>
      <div className="flex items-center gap-2 mt-2 text-xs text-slate-500">
        <span>⏱️ {Math.round(task.estimated_minutes / 60 * 10) / 10}h estimated</span>
        <span>·</span>
        <span>{formatDate(dueDate)}</span>
      </div>
    </div>
  );
}

function formatDate(date: Date): string {
  return date.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

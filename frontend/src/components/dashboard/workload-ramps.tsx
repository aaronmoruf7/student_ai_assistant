"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface WeekData {
  week_label: string;
  work_hours: number;
  available_hours: number;
  utilization: number;
  load_level: string;
  emoji: string;
  tasks_due: number;
}

interface WorkloadRampsProps {
  weeks: WeekData[];
  isLoading?: boolean;
}

export function WorkloadRamps({ weeks, isLoading }: WorkloadRampsProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Workload Ramps</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="animate-pulse">
                <div className="h-4 bg-slate-200 rounded w-1/4 mb-2"></div>
                <div className="h-8 bg-slate-200 rounded"></div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Workload Ramps</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {weeks.map((week, index) => (
            <div key={index}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">
                  {week.emoji} {week.week_label}
                </span>
                <span className="text-xs text-slate-500">
                  {week.tasks_due} tasks · {week.work_hours}h / {week.available_hours}h
                </span>
              </div>
              <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${getBarColor(week.load_level)}`}
                  style={{ width: `${Math.min(week.utilization * 100, 100)}%` }}
                />
              </div>
              {week.utilization > 1 && (
                <p className="text-xs text-red-500 mt-1">
                  ⚠️ Overloaded by {Math.round((week.utilization - 1) * week.available_hours)}h
                </p>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function getBarColor(level: string): string {
  switch (level) {
    case "light":
      return "bg-green-500";
    case "medium":
      return "bg-yellow-500";
    case "heavy":
      return "bg-orange-500";
    case "overloaded":
      return "bg-red-500";
    default:
      return "bg-slate-400";
  }
}

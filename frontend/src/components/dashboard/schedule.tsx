"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

interface WorkBlock {
  id: string;
  title: string;
  start: string;
  end: string;
  duration_minutes: number;
  status: string;
}

interface ScheduleProps {
  blocks: WorkBlock[];
  isLoading?: boolean;
  onGeneratePlan?: () => void;
  isGenerating?: boolean;
}

export function Schedule({
  blocks,
  isLoading,
  onGeneratePlan,
  isGenerating,
}: ScheduleProps) {
  // Group blocks by day
  const blocksByDay = groupBlocksByDay(blocks);
  const days = Object.keys(blocksByDay).sort();

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Your Schedule</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="animate-pulse">
                <div className="h-4 bg-slate-200 rounded w-1/4 mb-2"></div>
                <div className="h-16 bg-slate-200 rounded"></div>
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
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Your Schedule</CardTitle>
          <Button
            size="sm"
            onClick={onGeneratePlan}
            disabled={isGenerating}
          >
            {isGenerating ? "Generating..." : "Generate Plan"}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {blocks.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-slate-500 mb-4">No study blocks scheduled yet</p>
            <Button onClick={onGeneratePlan} disabled={isGenerating}>
              {isGenerating ? "Generating..." : "Generate Study Plan"}
            </Button>
          </div>
        ) : (
          <ScrollArea className="h-[300px] pr-4">
            <div className="space-y-4">
              {days.map((day) => (
                <div key={day}>
                  <h4 className="text-sm font-medium text-slate-500 mb-2">
                    {formatDayHeader(day)}
                  </h4>
                  <div className="space-y-2">
                    {blocksByDay[day].map((block) => (
                      <BlockItem key={block.id} block={block} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}

function BlockItem({ block }: { block: WorkBlock }) {
  const start = new Date(block.start);
  const end = new Date(block.end);

  return (
    <div className="flex items-center gap-3 p-3 bg-blue-50 border border-blue-200 rounded-lg">
      <div className="text-center shrink-0">
        <p className="text-xs font-medium text-blue-600">
          {formatTime(start)}
        </p>
        <p className="text-xs text-slate-400">to</p>
        <p className="text-xs font-medium text-blue-600">
          {formatTime(end)}
        </p>
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{block.title}</p>
        <p className="text-xs text-slate-500">
          {block.duration_minutes} min
        </p>
      </div>
      <Badge
        variant={block.status === "completed" ? "default" : "secondary"}
        className="shrink-0"
      >
        {block.status}
      </Badge>
    </div>
  );
}

function groupBlocksByDay(blocks: WorkBlock[]): Record<string, WorkBlock[]> {
  const grouped: Record<string, WorkBlock[]> = {};

  for (const block of blocks) {
    const day = new Date(block.start).toISOString().split("T")[0];
    if (!grouped[day]) {
      grouped[day] = [];
    }
    grouped[day].push(block);
  }

  // Sort blocks within each day
  for (const day of Object.keys(grouped)) {
    grouped[day].sort(
      (a, b) => new Date(a.start).getTime() - new Date(b.start).getTime()
    );
  }

  return grouped;
}

function formatDayHeader(dateStr: string): string {
  const date = new Date(dateStr);
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  if (date.toDateString() === today.toDateString()) {
    return "Today";
  }
  if (date.toDateString() === tomorrow.toDateString()) {
    return "Tomorrow";
  }

  return date.toLocaleDateString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState, useCallback } from "react";

import { Header } from "@/components/dashboard/header";
import { WorkloadRamps } from "@/components/dashboard/workload-ramps";
import { TaskList } from "@/components/dashboard/task-list";
import { Schedule } from "@/components/dashboard/schedule";
import { ChatPanel } from "@/components/dashboard/chat-panel";

import {
  getWorkloadRamps,
  getTasks,
  getWorkBlocks,
  generatePlan,
  syncAll,
} from "@/lib/api";

export default function Home() {
  const { data: session, status } = useSession();
  const router = useRouter();

  const [isLoading, setIsLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  const [workloadData, setWorkloadData] = useState<any>(null);
  const [tasksData, setTasksData] = useState<any>(null);
  const [blocksData, setBlocksData] = useState<any>(null);

  const userId = session?.user?.id;

  const fetchData = useCallback(async () => {
    if (!userId) return;

    setIsLoading(true);
    try {
      const [workload, tasks, blocks] = await Promise.all([
        getWorkloadRamps(userId, 4),
        getTasks(userId),
        getWorkBlocks(userId, 2),
      ]);

      setWorkloadData(workload);
      setTasksData(tasks);
      setBlocksData(blocks);
    } catch (error) {
      console.error("Error fetching data:", error);
    } finally {
      setIsLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/login");
    }
  }, [status, router]);

  useEffect(() => {
    if (userId) {
      fetchData();
    }
  }, [userId, fetchData]);

  const handleSync = async () => {
    if (!userId) return;

    setIsSyncing(true);
    try {
      await syncAll(userId);
      await fetchData();
    } catch (error) {
      console.error("Sync error:", error);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleGeneratePlan = async () => {
    if (!userId) return;

    setIsGenerating(true);
    try {
      await generatePlan(userId, 1, false);
      const blocks = await getWorkBlocks(userId, 2);
      setBlocksData(blocks);
    } catch (error) {
      console.error("Generate plan error:", error);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleChatAction = (action: string) => {
    switch (action) {
      case "generatePlan":
        handleGeneratePlan();
        break;
      case "sync":
        handleSync();
        break;
    }
  };

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="text-center">
          <div className="text-4xl mb-4">📚</div>
          <p className="text-slate-600">Loading...</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return null;
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Header
        userName={session.user?.name || "User"}
        userEmail={session.user?.email || ""}
        onSync={handleSync}
        isSyncing={isSyncing}
      />

      <main className="flex-1 container mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full">
          {/* Left column - Workload + Tasks */}
          <div className="lg:col-span-2 space-y-6">
            <WorkloadRamps
              weeks={workloadData?.weeks || []}
              isLoading={isLoading}
            />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <TaskList
                tasks={tasksData?.tasks || []}
                isLoading={isLoading}
              />

              <Schedule
                blocks={blocksData?.blocks || []}
                isLoading={isLoading}
                onGeneratePlan={handleGeneratePlan}
                isGenerating={isGenerating}
              />
            </div>
          </div>

          {/* Right column - Chat */}
          <div className="lg:col-span-1">
            <div className="sticky top-6">
              <ChatPanel
                userId={userId}
                onAction={handleChatAction}
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

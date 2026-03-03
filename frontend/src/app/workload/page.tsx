"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import Link from "next/link";

export default function WorkloadPage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") router.push("/login");
  }, [status, router]);

  if (status === "loading") {
    return <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-400">Loading...</div>;
  }

  if (!session) return null;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="container mx-auto px-4 py-3 flex items-center gap-4">
          <Link href="/" className="text-slate-500 hover:text-slate-700 text-sm">← Dashboard</Link>
          <h1 className="font-semibold text-lg">Workload Forecast</h1>
        </div>
      </header>

      <main className="container mx-auto px-4 py-12 text-center text-slate-400">
        <p className="text-lg font-medium mb-2">Coming soon</p>
        <p className="text-sm">Generate a workload forecasting prompt to paste into your LLM and see upcoming heavy weeks.</p>
      </main>
    </div>
  );
}

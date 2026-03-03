"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import { signOut } from "next-auth/react";

interface HeaderProps {
  userName?: string;
  userEmail?: string;
  onSync?: () => void;
  isSyncing?: boolean;
}

export function Header({ userName, userEmail, onSync, isSyncing }: HeaderProps) {
  return (
    <header className="border-b bg-white">
      <div className="container mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="text-2xl">📚</div>
          <div>
            <h1 className="font-semibold text-lg">Student AI Assistant</h1>
            <p className="text-xs text-slate-500">Your study companion</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <Link href="/tasks">
            <Button variant="outline" size="sm">Tasks</Button>
          </Link>

          <Link href="/estimate">
            <Button variant="outline" size="sm">Estimate</Button>
          </Link>

          <Link href="/settings">
            <Button variant="outline" size="sm">Settings</Button>
          </Link>

          <Link href="/setup">
            <Button variant="outline" size="sm">⚙️ Setup</Button>
          </Link>

          <Link href="/data">
            <Button variant="outline" size="sm">Data</Button>
          </Link>

          <Link href="/preferences">
            <Button variant="outline" size="sm">Preferences</Button>
          </Link>

          <Link href="/plan">
            <Button variant="outline" size="sm">Plan</Button>
          </Link>

          <Link href="/workload">
            <Button variant="outline" size="sm">Workload</Button>
          </Link>

          <Button
            variant="outline"
            size="sm"
            onClick={onSync}
            disabled={isSyncing}
          >
            {isSyncing ? "Syncing..." : "🔄 Sync"}
          </Button>

          <div className="flex items-center gap-3">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-medium">{userName}</p>
              <p className="text-xs text-slate-500">{userEmail}</p>
            </div>
            <Avatar className="h-9 w-9 bg-slate-200 flex items-center justify-center">
              <span>{userName?.[0]?.toUpperCase() || "U"}</span>
            </Avatar>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => signOut({ callbackUrl: "/login" })}
            >
              Sign out
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
}

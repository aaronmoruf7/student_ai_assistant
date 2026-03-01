"use client";

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

"use client";

import { useState, useRef, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { sendChatMessage, type ChatMessage, type ToolAction } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  actions?: ToolAction[];
};

interface ChatPanelProps {
  userId?: string;
}

// ---------------------------------------------------------------------------
// Tool action badge
// ---------------------------------------------------------------------------

function ActionBadge({ action }: { action: ToolAction }) {
  const icon = action.success ? "✓" : "✗";
  const color = action.success
    ? "bg-green-50 text-green-700 border-green-200"
    : "bg-red-50 text-red-700 border-red-200";

  return (
    <div className={`text-xs px-2 py-1 rounded border mt-1 flex items-center gap-1.5 ${color}`}>
      <span className="font-semibold">{icon}</span>
      <span>{action.label}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Individual message bubble
// ---------------------------------------------------------------------------

function ChatBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex items-start gap-2 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`w-7 h-7 rounded-full flex items-center justify-center text-sm shrink-0 ${
          isUser ? "bg-slate-200" : "bg-blue-100"
        }`}
      >
        {isUser ? "👤" : "🤖"}
      </div>

      <div className={`max-w-[85%] ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        <div
          className={`rounded-2xl px-3 py-2 text-sm ${
            isUser
              ? "bg-blue-500 text-white rounded-tr-sm"
              : "bg-slate-100 text-slate-800 rounded-tl-sm"
          }`}
        >
          <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
        </div>

        {/* Tool action badges */}
        {message.actions && message.actions.length > 0 && (
          <div className="mt-1 w-full space-y-0.5">
            {message.actions.map((a, i) => (
              <ActionBadge key={i} action={a} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main ChatPanel
// ---------------------------------------------------------------------------

export function ChatPanel({ userId }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  // Kick off the AI's opening message when the panel mounts
  useEffect(() => {
    if (!userId) return;
    (async () => {
      setIsInitializing(true);
      try {
        setMessages([
          {
            id: "opening",
            role: "assistant",
            content: "Hey! I'm your planning assistant. Tell me what you need.",
          },
        ]);
        // const result = await sendChatMessage(userId, []);
        // setMessages([
        //   {
        //     id: "opening",
        //     role: "assistant",
        //     content: result.reply,
        //     actions: result.actions,
        //   },
        // ]);
      } catch {
        setMessages([
          {
            id: "opening",
            role: "assistant",
            content: "Hey! I'm your planning assistant. Tell me what you need.",
          },
        ]);
      } finally {
        setIsInitializing(false);
      }
    })();
  }, [userId]);

  const handleSend = async () => {
    if (!input.trim() || isLoading || !userId) return;

    const userText = input.trim();
    setInput("");

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: userText,
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    // Build history to send (exclude the opening message metadata, just role+content)
    const history: ChatMessage[] = [...messages, userMsg].map((m) => ({
      role: m.role,
      content: m.content,
    }));

    try {
      const result = await sendChatMessage(userId, history);

      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: result.reply,
          actions: result.actions,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: "Something went wrong. Please try again.",
        },
      ]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-2 shrink-0">
        <CardTitle className="text-base flex items-center gap-2">
          <span>🤖</span>
          Planning Assistant
        </CardTitle>
      </CardHeader>

      <CardContent className="flex-1 flex flex-col min-h-0 gap-3">
        {/* Message list */}
        <ScrollArea className="flex-1" ref={scrollRef}>
          <div className="space-y-4 pr-2">
            {isInitializing ? (
              <div className="flex items-start gap-2">
                <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center text-sm shrink-0">
                  🤖
                </div>
                <div className="bg-slate-100 rounded-2xl rounded-tl-sm px-3 py-2">
                  <div className="flex gap-1">
                    {[0, 100, 200].map((delay) => (
                      <span
                        key={delay}
                        className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"
                        style={{ animationDelay: `${delay}ms` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              messages.map((m) => <ChatBubble key={m.id} message={m} />)
            )}

            {isLoading && (
              <div className="flex items-start gap-2">
                <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center text-sm shrink-0">
                  🤖
                </div>
                <div className="bg-slate-100 rounded-2xl rounded-tl-sm px-3 py-2">
                  <div className="flex gap-1">
                    {[0, 100, 200].map((delay) => (
                      <span
                        key={delay}
                        className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce"
                        style={{ animationDelay: `${delay}ms` }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </ScrollArea>

        {/* Input */}
        <div className="flex gap-2 shrink-0 pt-2 border-t">
          <Input
            ref={inputRef}
            placeholder="Tell me what you need..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            disabled={isLoading || isInitializing}
            className="text-sm"
          />
          <Button
            onClick={handleSend}
            disabled={isLoading || isInitializing || !input.trim()}
            size="sm"
          >
            Send
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

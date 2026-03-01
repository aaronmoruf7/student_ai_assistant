"use client";

import { useState, useRef, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar } from "@/components/ui/avatar";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface ChatPanelProps {
  userId?: string;
  onAction?: (action: string, params?: Record<string, unknown>) => void;
}

export function ChatPanel({ userId, onAction }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi! I'm your study assistant. I can help you understand your workload, plan your week, or answer questions about your tasks. What would you like to know?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      // For now, use a simple pattern matching for common actions
      // Later, this will call an AI endpoint
      const response = await getAIResponse(userMessage.content, userId, onAction);

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: response,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "Sorry, I encountered an error. Please try again.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <span className="text-xl">🤖</span>
          Study Assistant
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col min-h-0">
        <ScrollArea className="flex-1 pr-4" ref={scrollRef}>
          <div className="space-y-4">
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
            {isLoading && (
              <div className="flex items-start gap-3">
                <Avatar className="h-8 w-8 bg-blue-100 flex items-center justify-center">
                  <span className="text-sm">🤖</span>
                </Avatar>
                <div className="bg-slate-100 rounded-lg px-3 py-2">
                  <div className="flex gap-1">
                    <span className="animate-bounce">●</span>
                    <span className="animate-bounce" style={{ animationDelay: "0.1s" }}>●</span>
                    <span className="animate-bounce" style={{ animationDelay: "0.2s" }}>●</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </ScrollArea>

        <div className="flex gap-2 mt-4 pt-4 border-t">
          <Input
            placeholder="Ask me anything..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            disabled={isLoading}
          />
          <Button onClick={handleSend} disabled={isLoading || !input.trim()}>
            Send
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ChatMessage({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex items-start gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <Avatar className={`h-8 w-8 flex items-center justify-center ${isUser ? "bg-slate-200" : "bg-blue-100"}`}>
        <span className="text-sm">{isUser ? "👤" : "🤖"}</span>
      </Avatar>
      <div
        className={`rounded-lg px-3 py-2 max-w-[80%] ${
          isUser ? "bg-blue-500 text-white" : "bg-slate-100"
        }`}
      >
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
      </div>
    </div>
  );
}

// Simple pattern-based responses for now
// Will be replaced with actual AI endpoint
async function getAIResponse(
  message: string,
  userId?: string,
  onAction?: (action: string, params?: Record<string, unknown>) => void
): Promise<string> {
  const lowerMessage = message.toLowerCase();

  // Simulate network delay
  await new Promise((resolve) => setTimeout(resolve, 500));

  if (lowerMessage.includes("generate") && lowerMessage.includes("plan")) {
    onAction?.("generatePlan");
    return "I'm generating your study plan now! This will create study blocks based on your upcoming tasks and available time.";
  }

  if (lowerMessage.includes("sync") || lowerMessage.includes("refresh")) {
    onAction?.("sync");
    return "I'm syncing your data from Canvas and Google Calendar. This will update your tasks and events.";
  }

  if (lowerMessage.includes("heavy") || lowerMessage.includes("busy") || lowerMessage.includes("workload")) {
    return "Looking at your workload ramps on the left, you can see which weeks are heaviest. The bars show how much work you have compared to your available time. Red means you're overloaded!";
  }

  if (lowerMessage.includes("task") || lowerMessage.includes("assignment")) {
    return "Your upcoming tasks are shown in the 'Upcoming Tasks' section. Tasks are sorted by due date, with the most urgent ones highlighted. I estimate how long each will take based on the points and type.";
  }

  if (lowerMessage.includes("schedule") || lowerMessage.includes("block")) {
    return "Your schedule shows the study blocks I've planned for you. Click 'Generate Plan' to create a new schedule based on your tasks and free time. I'll automatically avoid your classes, meals, and sleep time.";
  }

  if (lowerMessage.includes("help") || lowerMessage.includes("what can you")) {
    return `I can help you with:

• **View workload**: "How busy am I this week?"
• **Generate plan**: "Create a study schedule"
• **Sync data**: "Refresh my tasks and calendar"
• **Understand tasks**: "What's due soon?"

Just ask naturally, and I'll do my best to help!`;
  }

  return "I understand you're asking about your studies. Could you be more specific? I can help with your workload, schedule, tasks, or generate a study plan.";
}

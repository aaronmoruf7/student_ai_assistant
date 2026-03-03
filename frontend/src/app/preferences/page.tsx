"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getUserProfile, savePreferences } from "@/lib/api";

// ─── The prompt users copy into their own LLM ────────────────────────────────

const GATHERING_PROMPT = `You are helping me build a structured profile so I can automatically plan my week as a student. Please interview me by asking about each topic below — one at a time, conversationally. Don't ask them all at once.

Topics to cover:
1. Sleep — What time do I usually go to sleep and wake up on weekdays? Weekends?
2. Meals — When do I usually eat breakfast, lunch, and dinner? Do I cook, go out, or eat on campus?
3. Focus style — Do I prefer long deep-work sessions or shorter focused blocks (e.g. Pomodoro 25/5)? How long can I concentrate before I need a break?
4. Breaks — What do I do during breaks? How long do I like them?
5. Peak hours — When am I most productive: morning, afternoon, or evening?
6. School time — How many hours per week do I realistically want to spend on coursework?
7. Outside commitments — What am I involved in outside of class? (internships, clubs, recruiting, gym, part-time job, research, etc.) Roughly how many hours per week does each take?
8. Goals — What are my top 2–3 goals this semester? (GPA, landing an internship, learning a skill, etc.)
9. Anything else — Is there anything else about how I like to work or what matters to me week-to-week that would help in planning?

After we've covered everything, output a clean structured summary under this exact heading:

=== MY PREFERENCES ===

Write it in clear paragraphs or bullet points. I'll copy and paste just that section back into my planning app.`;

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PreferencesPage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  const [current, setCurrent] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saved" | "error">("idle");
  const [promptCopied, setPromptCopied] = useState(false);

  useEffect(() => {
    if (status === "unauthenticated") router.push("/login");
  }, [status, router]);

  const userId = (session?.user as any)?.id;

  useEffect(() => {
    if (!userId) return;
    getUserProfile(userId)
      .then((p) => {
        setCurrent(p.ai_preferences);
        if (p.ai_preferences) setDraft(p.ai_preferences);
      })
      .finally(() => setLoading(false));
  }, [userId]);

  const copyPrompt = async () => {
    await navigator.clipboard.writeText(GATHERING_PROMPT);
    setPromptCopied(true);
    setTimeout(() => setPromptCopied(false), 2500);
  };

  const handleSave = async () => {
    if (!userId || !draft.trim()) return;
    setSaving(true);
    setSaveStatus("idle");
    try {
      await savePreferences(userId, draft.trim());
      setCurrent(draft.trim());
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 3000);
    } catch {
      setSaveStatus("error");
    } finally {
      setSaving(false);
    }
  };

  if (status === "loading" || loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-400">
        Loading...
      </div>
    );
  }

  if (!session) return null;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="container mx-auto px-4 py-3 flex items-center gap-4">
          <Link href="/" className="text-slate-500 hover:text-slate-700 text-sm">
            ← Dashboard
          </Link>
          <h1 className="font-semibold text-lg">Preferences</h1>
          {current && (
            <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
              Saved
            </span>
          )}
        </div>
      </header>

      <main className="container mx-auto px-4 py-6 space-y-6 max-w-3xl">

        {/* Step 1 */}
        <section className="bg-white rounded-lg border">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <div>
              <h2 className="font-semibold text-slate-800">
                Step 1 — Copy this prompt into your LLM
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Paste it into ChatGPT, Claude, or any LLM and answer its questions.
                At the end, copy the <code className="bg-slate-100 px-1 rounded">{"=== MY PREFERENCES ==="}</code> section it outputs.
              </p>
            </div>
            <button
              onClick={copyPrompt}
              className="px-3 py-1.5 text-sm border border-slate-300 rounded hover:border-slate-500 transition-colors whitespace-nowrap"
            >
              {promptCopied ? "✓ Copied" : "Copy Prompt"}
            </button>
          </div>
          <pre className="p-4 text-xs text-slate-600 font-mono whitespace-pre-wrap leading-relaxed max-h-72 overflow-auto">
            {GATHERING_PROMPT}
          </pre>
        </section>

        {/* Step 2 */}
        <section className="bg-white rounded-lg border">
          <div className="px-4 py-3 border-b">
            <h2 className="font-semibold text-slate-800">
              Step 2 — Paste the LLM's output here
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Copy everything under <code className="bg-slate-100 px-1 rounded">{"=== MY PREFERENCES ==="}</code> and paste it below.
            </p>
          </div>
          <div className="p-4 space-y-3">
            <textarea
              value={draft}
              onChange={(e) => { setDraft(e.target.value); setSaveStatus("idle"); }}
              placeholder="Paste your LLM's preference summary here..."
              rows={12}
              className="w-full text-sm font-mono border border-slate-200 rounded-lg p-3 resize-y focus:outline-none focus:border-slate-400 text-slate-700 placeholder:text-slate-300"
            />
            <div className="flex items-center gap-3">
              <button
                onClick={handleSave}
                disabled={saving || !draft.trim()}
                className="px-4 py-2 bg-slate-800 text-white text-sm rounded hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {saving ? "Saving..." : "Save Preferences"}
              </button>
              {saveStatus === "saved" && (
                <span className="text-sm text-green-600">✓ Saved — will appear in your Data Hub</span>
              )}
              {saveStatus === "error" && (
                <span className="text-sm text-red-500">Failed to save. Try again.</span>
              )}
            </div>
          </div>
        </section>

        {/* Current saved (if different from draft) */}
        {current && current !== draft.trim() && (
          <section className="bg-white rounded-lg border border-slate-200">
            <div className="px-4 py-3 border-b">
              <h2 className="font-semibold text-slate-700 text-sm">Currently saved</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Your last saved preferences. Saving new text above will replace this.
              </p>
            </div>
            <pre className="p-4 text-xs text-slate-500 font-mono whitespace-pre-wrap leading-relaxed max-h-48 overflow-auto">
              {current}
            </pre>
          </section>
        )}

      </main>
    </div>
  );
}

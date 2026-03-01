"use client";

import { useSession, signOut } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function Home() {
  const { data: session, status } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/login");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-600">Loading...</p>
      </div>
    );
  }

  if (!session) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-2xl font-bold text-gray-900">
              Student AI Assistant
            </h1>
            <button
              onClick={() => signOut({ callbackUrl: "/login" })}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
            >
              Sign out
            </button>
          </div>

          <div className="space-y-4">
            <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
              <p className="text-green-800">
                Signed in as <strong>{session.user?.name}</strong> ({session.user?.email})
              </p>
            </div>

            <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
              <h2 className="font-semibold text-gray-900 mb-2">Integration Status</h2>
              <ul className="space-y-2 text-sm">
                <li className="flex items-center gap-2">
                  <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                  Google Calendar: Connected
                </li>
                <li className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${session.user?.hasCanvas ? "bg-green-500" : "bg-yellow-500"}`}></span>
                  Canvas: {session.user?.hasCanvas ? "Connected" : "Not connected"}
                </li>
              </ul>
            </div>

            {!session.user?.hasCanvas && (
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <p className="text-blue-800 text-sm">
                  Connect your Canvas account to sync courses and assignments.
                </p>
                <button className="mt-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
                  Connect Canvas
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

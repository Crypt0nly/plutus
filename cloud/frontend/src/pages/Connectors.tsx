import { useAuth } from "@clerk/clerk-react";
import { useState } from "react";

const CONNECTORS = [
  { id: "telegram", name: "Telegram", icon: "✈️" },
  { id: "github", name: "GitHub", icon: "🐙" },
  { id: "gmail", name: "Gmail", icon: "📧" },
  { id: "google_calendar", name: "Google Calendar", icon: "📅" },
  { id: "discord", name: "Discord", icon: "🎮" },
  { id: "slack", name: "Slack", icon: "💬" },
  { id: "email", name: "Email (SMTP)", icon: "📨" },
];

export default function Connectors() {
  const { getToken } = useAuth();
  const [connected, setConnected] = useState<Record<string, boolean>>({});

  const handleConfigure = async (id: string) => {
    // TODO: implement connector OAuth / config flows
    const token = await getToken();
    console.log("Configure connector:", id, "token:", token);
    setConnected((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white p-8">
      <h1 className="text-2xl font-bold mb-2">Connectors</h1>
      <p className="text-gray-400 mb-8">Manage your service integrations</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {CONNECTORS.map(({ id, name, icon }) => (
          <div
            key={id}
            className="bg-gray-800 border border-gray-700 rounded-xl p-5 flex flex-col gap-3"
          >
            <div className="flex items-center gap-3">
              <span className="text-3xl">{icon}</span>
              <div>
                <div className="font-semibold">{name}</div>
                <div className={`text-xs ${connected[id] ? "text-green-400" : "text-gray-500"}`}>
                  {connected[id] ? "● Connected" : "○ Not Connected"}
                </div>
              </div>
            </div>
            <button
              onClick={() => handleConfigure(id)}
              className="mt-auto w-full py-1.5 rounded-lg border border-amber-500 text-amber-400 text-sm font-medium hover:bg-amber-500 hover:text-gray-900 transition-colors"
            >
              Configure
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

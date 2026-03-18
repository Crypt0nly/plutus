import { useEffect, useState } from "react";
import { useAuth } from "@clerk/clerk-react";
import { Trash2 } from "lucide-react";

interface Fact { id: number; content: string; category: string; created_at: string; }

export default function Memory() {
  const { getToken } = useAuth();
  const [facts, setFacts] = useState<Fact[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const token = await getToken();
      const res = await fetch("/api/agents/memory", { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      setFacts(data.memories ?? data.facts ?? []);
      setLoading(false);
    })();
  }, []);

  const deleteFact = async (id: number) => {
    const token = await getToken();
    await fetch(`/api/agents/memory/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
    setFacts(f => f.filter(x => x.id !== id));
  };

  const filtered = facts.filter(f => f.content.toLowerCase().includes(query.toLowerCase()) || f.category.toLowerCase().includes(query.toLowerCase()));
  const grouped = filtered.reduce<Record<string, Fact[]>>((acc, f) => ({ ...acc, [f.category]: [...(acc[f.category] ?? []), f] }), {});

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-6">
      <h1 className="text-2xl font-bold text-amber-400 mb-4">Agent Memory</h1>
      <input
        className="w-full mb-6 px-4 py-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-100 placeholder-gray-500 focus:outline-none focus:border-amber-500"
        placeholder="Search memories…" value={query} onChange={e => setQuery(e.target.value)}
      />
      {loading ? (
        <p className="text-gray-500 text-center mt-20">Loading…</p>
      ) : Object.keys(grouped).length === 0 ? (
        <p className="text-gray-500 text-center mt-20">No memories found.</p>
      ) : Object.entries(grouped).map(([cat, items]) => (
        <div key={cat} className="mb-6">
          <h2 className="text-sm font-semibold text-amber-500 uppercase tracking-wider mb-2">{cat}</h2>
          <div className="space-y-2">
            {items.map(f => (
              <div key={f.id} className="flex items-start justify-between bg-gray-800 border border-gray-700 rounded-lg px-4 py-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-100 leading-snug">{f.content}</p>
                  <p className="text-xs text-gray-500 mt-1">{new Date(f.created_at).toLocaleDateString()}</p>
                </div>
                <button onClick={() => deleteFact(f.id)} className="ml-3 text-gray-600 hover:text-red-400 transition-colors flex-shrink-0">
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

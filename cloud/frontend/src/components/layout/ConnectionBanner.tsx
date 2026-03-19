import { useAppStore } from "../../stores/appStore";
import { WifiOff, Loader2 } from "lucide-react";

export function ConnectionBanner() {
  const connected = useAppStore((s) => s.connected);

  if (connected) return null;

  return (
    <div className="flex items-center gap-3 px-5 py-2.5 text-sm flex-shrink-0"
      style={{
        background: "rgba(239, 68, 68, 0.06)",
        borderBottom: "1px solid rgba(239, 68, 68, 0.15)"
      }}
    >
      <WifiOff className="w-3.5 h-3.5 text-red-400 shrink-0" />
      <span className="text-red-400 text-xs">
        Connection lost — the Plutus backend is unreachable.
      </span>
      <div className="flex items-center gap-1.5 ml-auto">
        <Loader2 className="w-3 h-3 text-red-400/60 animate-spin" />
        <span className="text-[11px] text-red-400/60">Retrying…</span>
      </div>
    </div>
  );
}

import { useAppStore } from "../../stores/appStore";
import { WifiOff } from "lucide-react";

export function ConnectionBanner() {
  const connected = useAppStore((s) => s.connected);

  if (connected) return null;

  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-red-400 text-sm">
      <WifiOff className="w-4 h-4 shrink-0" />
      <span>
        Connection lost — the Plutus backend is unreachable. Retrying in the background&hellip;
      </span>
    </div>
  );
}

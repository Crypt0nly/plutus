import type { LucideIcon } from "lucide-react";

interface Props {
  icon: LucideIcon;
  label: string;
  value: string;
  sublabel?: string;
  color: string;
  capitalize?: boolean;
}

const colorMap: Record<string, { icon: string; glow: string }> = {
  emerald: { icon: "bg-emerald-500/10 text-emerald-400", glow: "shadow-emerald-500/5" },
  red: { icon: "bg-red-500/10 text-red-400", glow: "shadow-red-500/5" },
  plutus: { icon: "bg-plutus-500/10 text-plutus-400", glow: "shadow-plutus-500/5" },
  blue: { icon: "bg-blue-500/10 text-blue-400", glow: "shadow-blue-500/5" },
  gray: { icon: "bg-gray-500/10 text-gray-400", glow: "" },
  amber: { icon: "bg-amber-500/10 text-amber-400", glow: "shadow-amber-500/5" },
  purple: { icon: "bg-purple-500/10 text-purple-400", glow: "shadow-purple-500/5" },
  rose: { icon: "bg-rose-500/10 text-rose-400", glow: "shadow-rose-500/5" },
};

export function StatusCard({ icon: Icon, label, value, sublabel, color, capitalize }: Props) {
  const colors = colorMap[color] || colorMap.gray;
  return (
    <div className={`bg-surface rounded-xl border border-gray-800/60 p-4 ${colors.glow}`}>
      <div className="flex items-center justify-between mb-3">
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${colors.icon}`}>
          <Icon className="w-4.5 h-4.5" />
        </div>
      </div>
      <p className={`text-2xl font-bold text-gray-100 tracking-tight ${capitalize ? "capitalize" : ""}`}>
        {value}
      </p>
      <p className="text-xs text-gray-500 mt-0.5">{label}</p>
      {sublabel && <p className="text-[10px] text-gray-600 mt-1">{sublabel}</p>}
    </div>
  );
}

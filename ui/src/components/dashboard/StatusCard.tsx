import type { LucideIcon } from "lucide-react";

interface Props {
  icon: LucideIcon;
  label: string;
  value: string;
  sublabel?: string;
  color: string;
  capitalize?: boolean;
}

const colorMap: Record<string, { iconColor: string; bg: string; border: string; glow: string }> = {
  emerald: {
    iconColor: "#34d399",
    bg: "rgba(16, 185, 129, 0.08)",
    border: "rgba(16, 185, 129, 0.15)",
    glow: "rgba(16, 185, 129, 0.1)"
  },
  red: {
    iconColor: "#f87171",
    bg: "rgba(239, 68, 68, 0.08)",
    border: "rgba(239, 68, 68, 0.15)",
    glow: "rgba(239, 68, 68, 0.1)"
  },
  plutus: {
    iconColor: "#818cf8",
    bg: "rgba(99, 102, 241, 0.08)",
    border: "rgba(99, 102, 241, 0.15)",
    glow: "rgba(99, 102, 241, 0.1)"
  },
  blue: {
    iconColor: "#60a5fa",
    bg: "rgba(59, 130, 246, 0.08)",
    border: "rgba(59, 130, 246, 0.15)",
    glow: "rgba(59, 130, 246, 0.1)"
  },
  gray: {
    iconColor: "#9ca3af",
    bg: "rgba(107, 114, 128, 0.08)",
    border: "rgba(107, 114, 128, 0.15)",
    glow: ""
  },
  amber: {
    iconColor: "#fbbf24",
    bg: "rgba(245, 158, 11, 0.08)",
    border: "rgba(245, 158, 11, 0.15)",
    glow: "rgba(245, 158, 11, 0.1)"
  },
  purple: {
    iconColor: "#c084fc",
    bg: "rgba(168, 85, 247, 0.08)",
    border: "rgba(168, 85, 247, 0.15)",
    glow: "rgba(168, 85, 247, 0.1)"
  },
  rose: {
    iconColor: "#fb7185",
    bg: "rgba(244, 63, 94, 0.08)",
    border: "rgba(244, 63, 94, 0.15)",
    glow: "rgba(244, 63, 94, 0.1)"
  },
};

export function StatusCard({ icon: Icon, label, value, sublabel, color, capitalize }: Props) {
  const colors = colorMap[color] || colorMap.gray;

  return (
    <div
      className="rounded-2xl p-4 transition-all duration-200 hover:scale-[1.01]"
      style={{
        background: "rgba(15, 18, 30, 0.8)",
        border: "1px solid rgba(255, 255, 255, 0.06)",
        boxShadow: colors.glow ? `0 4px 24px ${colors.glow}` : "0 4px 24px rgba(0,0,0,0.2)"
      }}
    >
      <div className="flex items-center justify-between mb-4">
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{ background: colors.bg, border: `1px solid ${colors.border}` }}
        >
          <Icon className="w-4 h-4" style={{ color: colors.iconColor }} />
        </div>
      </div>
      <p className={`text-2xl font-bold text-gray-100 tracking-tight leading-none ${capitalize ? "capitalize" : ""}`}>
        {value}
      </p>
      <p className="text-xs text-gray-500 mt-1.5">{label}</p>
      {sublabel && <p className="text-[10px] text-gray-700 mt-1">{sublabel}</p>}
    </div>
  );
}

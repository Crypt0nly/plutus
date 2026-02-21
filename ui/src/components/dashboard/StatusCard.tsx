import type { LucideIcon } from "lucide-react";

interface Props {
  icon: LucideIcon;
  label: string;
  value: string;
  color: string;
  capitalize?: boolean;
}

const colorMap: Record<string, string> = {
  emerald: "bg-emerald-500/10 text-emerald-400",
  red: "bg-red-500/10 text-red-400",
  plutus: "bg-plutus-500/10 text-plutus-400",
  blue: "bg-blue-500/10 text-blue-400",
  gray: "bg-gray-500/10 text-gray-400",
  amber: "bg-amber-500/10 text-amber-400",
};

export function StatusCard({ icon: Icon, label, value, color, capitalize }: Props) {
  const colorClasses = colorMap[color] || colorMap.gray;
  return (
    <div className="card flex items-center gap-4">
      <div
        className={`w-10 h-10 rounded-lg flex items-center justify-center ${colorClasses}`}
      >
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p
          className={`text-lg font-bold text-gray-200 ${
            capitalize ? "capitalize" : ""
          }`}
        >
          {value}
        </p>
        <p className="text-xs text-gray-500">{label}</p>
      </div>
    </div>
  );
}

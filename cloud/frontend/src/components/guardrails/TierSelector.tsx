import { Eye, UserCheck, Cog, Zap, Check } from "lucide-react";
import type { Tier, TierInfo } from "../../lib/types";

interface Props {
  tiers: TierInfo[];
  currentTier: Tier;
  onSelect: (tier: Tier) => void;
}

const tierIcons: Record<string, React.ElementType> = {
  observer: Eye,
  assistant: UserCheck,
  operator: Cog,
  autonomous: Zap,
};

const tierColors: Record<string, {
  ring: string;
  bg: string;
  bgStrong: string;
  text: string;
  glow: string;
  barFill: string;
}> = {
  observer: {
    ring: "ring-gray-400/50",
    bg: "bg-gray-500/10",
    bgStrong: "bg-gray-500/20",
    text: "text-gray-400",
    glow: "shadow-gray-500/10",
    barFill: "bg-gray-400/50",
  },
  assistant: {
    ring: "ring-blue-400/50",
    bg: "bg-blue-500/10",
    bgStrong: "bg-blue-500/20",
    text: "text-blue-400",
    glow: "shadow-blue-500/15",
    barFill: "bg-blue-400/50",
  },
  operator: {
    ring: "ring-plutus-400/50",
    bg: "bg-plutus-500/10",
    bgStrong: "bg-plutus-500/20",
    text: "text-plutus-400",
    glow: "shadow-plutus-500/15",
    barFill: "bg-plutus-400/50",
  },
  autonomous: {
    ring: "ring-amber-400/50",
    bg: "bg-amber-500/10",
    bgStrong: "bg-amber-500/20",
    text: "text-amber-400",
    glow: "shadow-amber-500/15",
    barFill: "bg-amber-400/50",
  },
};

export function TierSelector({ tiers, currentTier, onSelect }: Props) {
  return (
    <div className="grid grid-cols-4 gap-3">
      {tiers.map((tier) => {
        const Icon = tierIcons[tier.id] || Eye;
        const colors = tierColors[tier.id] || tierColors.observer;
        const active = tier.id === currentTier;

        return (
          <button
            key={tier.id}
            onClick={() => onSelect(tier.id)}
            className={`selector-card relative flex flex-col items-center gap-3 p-4 rounded-xl border-2 ${
              active
                ? `border-transparent ring-2 ${colors.ring} ${colors.bg} shadow-lg ${colors.glow}`
                : "border-gray-800/60 hover:border-gray-700/60 bg-gray-900/60 hover:bg-gray-800/40"
            }`}
            data-active={active}
          >
            {/* Active check indicator */}
            {active && (
              <div className="absolute top-2 right-2 w-5 h-5 rounded-full flex items-center justify-center bg-emerald-500/20">
                <Check className="w-3 h-3 text-emerald-400" />
              </div>
            )}

            {/* Icon */}
            <div
              className={`w-11 h-11 rounded-xl flex items-center justify-center transition-all duration-200 ${
                active ? colors.bgStrong : colors.bg
              }`}
            >
              <Icon className={`w-5 h-5 ${colors.text} transition-transform duration-200 ${
                active ? "scale-110" : ""
              }`} />
            </div>

            {/* Label + description */}
            <div className="text-center">
              <p
                className={`text-sm font-semibold transition-colors ${
                  active ? colors.text : "text-gray-300"
                }`}
              >
                {tier.label}
              </p>
              <p className="text-[11px] text-gray-500 mt-1 leading-relaxed">
                {tier.description}
              </p>
            </div>

            {/* Power level indicator — animated bars */}
            <div className="flex gap-1.5">
              {[0, 1, 2, 3].map((lvl) => (
                <div
                  key={lvl}
                  className={`h-1.5 rounded-full transition-all duration-300 ${
                    lvl <= tier.level
                      ? active
                        ? `w-7 ${colors.barFill}`
                        : `w-6 ${colors.bg}`
                      : "w-6 bg-gray-800/60"
                  }`}
                />
              ))}
            </div>
          </button>
        );
      })}
    </div>
  );
}

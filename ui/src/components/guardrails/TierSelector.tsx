import { Eye, UserCheck, Cog, Zap } from "lucide-react";
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

const tierColors: Record<string, { ring: string; bg: string; text: string }> = {
  observer: {
    ring: "ring-gray-500",
    bg: "bg-gray-500/10",
    text: "text-gray-400",
  },
  assistant: {
    ring: "ring-blue-500",
    bg: "bg-blue-500/10",
    text: "text-blue-400",
  },
  operator: {
    ring: "ring-plutus-500",
    bg: "bg-plutus-500/10",
    text: "text-plutus-400",
  },
  autonomous: {
    ring: "ring-amber-500",
    bg: "bg-amber-500/10",
    text: "text-amber-400",
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
            className={`relative flex flex-col items-center gap-3 p-4 rounded-xl border-2 transition-all ${
              active
                ? `border-transparent ring-2 ${colors.ring} ${colors.bg}`
                : "border-gray-800 hover:border-gray-700 bg-gray-900"
            }`}
          >
            {active && (
              <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-emerald-400" />
            )}
            <div
              className={`w-10 h-10 rounded-lg flex items-center justify-center ${colors.bg}`}
            >
              <Icon className={`w-5 h-5 ${colors.text}`} />
            </div>
            <div className="text-center">
              <p
                className={`text-sm font-semibold ${
                  active ? colors.text : "text-gray-300"
                }`}
              >
                {tier.label}
              </p>
              <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                {tier.description}
              </p>
            </div>
            {/* Power level indicator */}
            <div className="flex gap-1">
              {[0, 1, 2, 3].map((lvl) => (
                <div
                  key={lvl}
                  className={`w-6 h-1.5 rounded-full ${
                    lvl <= tier.level ? colors.bg.replace("/10", "/40") : "bg-gray-800"
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

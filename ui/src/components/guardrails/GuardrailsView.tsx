import { useEffect, useState } from "react";
import { Shield, Info } from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";
import { TierSelector } from "./TierSelector";
import { PermissionToggle } from "./PermissionToggle";
import type { TierInfo, Tier } from "../../lib/types";

export function GuardrailsView() {
  const { currentTier, setCurrentTier } = useAppStore();
  const [tiers, setTiers] = useState<TierInfo[]>([]);
  const [tools, setTools] = useState<Record<string, any>[]>([]);
  const [overrides, setOverrides] = useState<Record<string, any>>({});

  useEffect(() => {
    api.getGuardrails().then((data: any) => {
      setTiers(data.tier_info || []);
      setOverrides(data.overrides || {});
      if (data.current_tier) {
        setCurrentTier(data.current_tier);
      }
    }).catch(() => {});

    api.getTools().then((t: any) => setTools(t || [])).catch(() => {});
  }, [setCurrentTier]);

  const handleTierChange = async (tier: Tier) => {
    try {
      await api.setTier(tier);
      setCurrentTier(tier);
    } catch (e) {
      console.error("Failed to set tier:", e);
    }
  };

  const handleOverride = async (
    toolName: string,
    enabled: boolean,
    requireApproval: boolean
  ) => {
    try {
      await api.setToolOverride(toolName, enabled, requireApproval);
      setOverrides((prev) => ({
        ...prev,
        [toolName]: { enabled, require_approval: requireApproval },
      }));
    } catch (e) {
      console.error("Failed to set override:", e);
    }
  };

  const currentTierInfo = tiers.find((t) => t.id === currentTier);

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div>
        <h2 className="text-xl font-bold text-gray-100 mb-1">Guardrails</h2>
        <p className="text-sm text-gray-500">
          Control how much access Plutus has to your system
        </p>
      </div>

      {/* Info banner */}
      <div className="flex items-start gap-3 p-4 bg-plutus-600/10 border border-plutus-500/20 rounded-xl">
        <Info className="w-5 h-5 text-plutus-400 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-plutus-200">
          <p className="font-medium mb-1">How guardrails work</p>
          <p className="text-plutus-300/80">
            Choose a tier to set the baseline permissions, then fine-tune individual
            tools below. Higher tiers give the AI more autonomy. Every action is logged
            to the audit trail regardless of tier.
          </p>
        </div>
      </div>

      {/* Tier selector */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
          <Shield className="w-4 h-4 text-plutus-400" />
          Access Tier
        </h3>
        <TierSelector
          tiers={tiers}
          currentTier={currentTier}
          onSelect={handleTierChange}
        />
      </div>

      {/* Per-tool permissions */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">
          Tool Permissions
        </h3>
        <p className="text-xs text-gray-500 mb-4">
          Override the default permissions for the <strong className="text-gray-400 capitalize">{currentTier}</strong> tier.
          These overrides take priority over tier defaults.
        </p>
        <div className="space-y-3">
          {tools.map((tool) => {
            const tierPolicy = currentTierInfo?.tools[tool.name];
            const override = overrides[tool.name];

            return (
              <PermissionToggle
                key={tool.name}
                toolName={tool.name}
                description={tool.description}
                defaultPermission={tierPolicy?.permission || "denied"}
                override={override}
                onOverride={(enabled, requireApproval) =>
                  handleOverride(tool.name, enabled, requireApproval)
                }
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

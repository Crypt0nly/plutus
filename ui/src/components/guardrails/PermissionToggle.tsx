import { Terminal, HardDrive, Globe, Cpu, Monitor, Clipboard } from "lucide-react";

interface Props {
  toolName: string;
  description: string;
  defaultPermission: string;
  override?: { enabled: boolean; require_approval: boolean };
  onOverride: (enabled: boolean, requireApproval: boolean) => void;
}

const toolIcons: Record<string, React.ElementType> = {
  shell: Terminal,
  filesystem: HardDrive,
  browser: Globe,
  process: Cpu,
  system_info: Monitor,
  clipboard: Clipboard,
};

const permissionLabels: Record<string, { label: string; color: string }> = {
  allowed: { label: "Allowed", color: "text-emerald-400" },
  requires_approval: { label: "Needs Approval", color: "text-amber-400" },
  denied: { label: "Denied", color: "text-red-400" },
};

export function PermissionToggle({
  toolName,
  description,
  defaultPermission,
  override,
  onOverride,
}: Props) {
  const Icon = toolIcons[toolName] || Terminal;
  const isEnabled = override ? override.enabled : defaultPermission !== "denied";
  const needsApproval = override
    ? override.require_approval
    : defaultPermission === "requires_approval";

  const effectivePermission = !isEnabled
    ? "denied"
    : needsApproval
    ? "requires_approval"
    : "allowed";

  const perm = permissionLabels[effectivePermission] || permissionLabels.denied;

  return (
    <div className="flex items-center gap-4 p-3 bg-gray-800/50 rounded-lg border border-gray-800">
      {/* Icon + info */}
      <div className="w-9 h-9 rounded-lg bg-gray-800 flex items-center justify-center flex-shrink-0">
        <Icon className="w-4.5 h-4.5 text-gray-400" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-200">{toolName}</span>
          <span className={`text-xs ${perm.color}`}>{perm.label}</span>
        </div>
        <p className="text-xs text-gray-500 truncate">{description}</p>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-2 flex-shrink-0">
        {/* Approval toggle */}
        {isEnabled && (
          <button
            onClick={() => onOverride(true, !needsApproval)}
            className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
              needsApproval
                ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
                : "border-gray-700 bg-gray-800 text-gray-500 hover:text-gray-300"
            }`}
          >
            {needsApproval ? "Approval ON" : "Approval OFF"}
          </button>
        )}

        {/* Enable/disable toggle */}
        <button
          onClick={() => onOverride(!isEnabled, needsApproval)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            isEnabled ? "bg-plutus-600" : "bg-gray-700"
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              isEnabled ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
      </div>
    </div>
  );
}

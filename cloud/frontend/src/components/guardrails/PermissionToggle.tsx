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

const permissionLabels: Record<string, { label: string; color: string; bg: string }> = {
  allowed: { label: "Allowed", color: "text-emerald-400", bg: "bg-emerald-500/10" },
  requires_approval: { label: "Needs Approval", color: "text-amber-400", bg: "bg-amber-500/10" },
  denied: { label: "Denied", color: "text-red-400", bg: "bg-red-500/10" },
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
    <div className={`flex items-center gap-4 p-3.5 rounded-xl border transition-all duration-200 ${
      isEnabled
        ? "bg-gray-800/40 border-gray-700/50 hover:border-gray-600/50"
        : "bg-gray-800/20 border-gray-800/40 opacity-60 hover:opacity-80"
    }`}>
      {/* Icon + info */}
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${
        isEnabled ? "bg-gray-700/60" : "bg-gray-800/60"
      }`}>
        <Icon className={`w-[18px] h-[18px] transition-colors ${
          isEnabled ? "text-gray-300" : "text-gray-500"
        }`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-medium transition-colors ${
            isEnabled ? "text-gray-200" : "text-gray-400"
          }`}>{toolName}</span>
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${perm.color} ${perm.bg}`}>
            {perm.label}
          </span>
        </div>
        <p className="text-xs text-gray-500 truncate mt-0.5">{description}</p>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-2.5 flex-shrink-0">
        {/* Approval toggle */}
        {isEnabled && (
          <button
            onClick={() => onOverride(true, !needsApproval)}
            className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-all duration-200 ${
              needsApproval
                ? "border-amber-500/30 bg-amber-500/10 text-amber-400 hover:bg-amber-500/15 shadow-sm shadow-amber-500/5"
                : "border-gray-700/50 bg-gray-800/50 text-gray-500 hover:text-gray-300 hover:border-gray-600/50"
            }`}
          >
            {needsApproval ? "Approval ON" : "Approval OFF"}
          </button>
        )}

        {/* Enable/disable toggle — custom toggle switch */}
        <button
          onClick={() => onOverride(!isEnabled, needsApproval)}
          className={`toggle-switch ${isEnabled ? "" : ""}`}
          data-state={isEnabled ? "on" : "off"}
          role="switch"
          aria-checked={isEnabled}
        >
          <span className="toggle-thumb" />
        </button>
      </div>
    </div>
  );
}

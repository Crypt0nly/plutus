import { useState, useEffect, useCallback } from "react";
import {
  Download,
  X,
  ArrowUpCircle,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  Loader2,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";

type UpdatePhase =
  | { kind: "idle" }
  | { kind: "installing" }
  | { kind: "restarting"; newVersion: string }
  | { kind: "done"; newVersion: string }
  | { kind: "error"; message: string };

export function UpdateBanner() {
  const { updateInfo, setUpdateInfo } = useAppStore();
  const [phase, setPhase] = useState<UpdatePhase>({ kind: "idle" });
  const [showNotes, setShowNotes] = useState(false);

  if (!updateInfo || !updateInfo.available || updateInfo.dismissed) return null;

  const handleDismiss = async () => {
    try {
      await api.dismissUpdate(updateInfo.latestVersion);
    } catch {
      // still dismiss locally
    }
    setUpdateInfo({ ...updateInfo, dismissed: true });
  };

  const handleUpdate = async () => {
    setPhase({ kind: "installing" });
    try {
      const res = await api.applyUpdate();
      if (res.success) {
        const ver = res.new_version || updateInfo.latestVersion;
        if (res.restart_required) {
          setPhase({ kind: "restarting", newVersion: ver });
        } else {
          setPhase({ kind: "done", newVersion: ver });
        }
      } else {
        setPhase({
          kind: "error",
          message: res.error || "Update failed. Try updating manually.",
        });
      }
    } catch (e) {
      setPhase({
        kind: "error",
        message: e instanceof Error ? e.message : "Update failed",
      });
    }
  };

  return (
    <div className="shrink-0">
      {phase.kind === "idle" && (
        <IdleBanner
          updateInfo={updateInfo}
          showNotes={showNotes}
          onToggleNotes={() => setShowNotes(!showNotes)}
          onUpdate={handleUpdate}
          onDismiss={handleDismiss}
        />
      )}
      {phase.kind === "installing" && <InstallingBanner />}
      {phase.kind === "restarting" && (
        <RestartingBanner newVersion={phase.newVersion} />
      )}
      {phase.kind === "done" && (
        <DoneBanner
          newVersion={phase.newVersion}
          onClose={() => setUpdateInfo({ ...updateInfo, dismissed: true })}
        />
      )}
      {phase.kind === "error" && (
        <ErrorBanner
          message={phase.message}
          onRetry={() => setPhase({ kind: "idle" })}
          onClose={() => {
            setPhase({ kind: "idle" });
            setUpdateInfo({ ...updateInfo, dismissed: true });
          }}
        />
      )}
    </div>
  );
}

/* ── Sub-banners ─────────────────────────────────────────────────────────── */

function IdleBanner({
  updateInfo,
  showNotes,
  onToggleNotes,
  onUpdate,
  onDismiss,
}: {
  updateInfo: {
    available: boolean;
    dismissed: boolean;
    currentVersion: string;
    latestVersion: string;
    releaseName: string;
    releaseNotes: string;
    releaseUrl: string;
    publishedAt: string;
  };
  showNotes: boolean;
  onToggleNotes: () => void;
  onUpdate: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="bg-plutus-500/5 border-b border-plutus-500/20 px-4 py-2.5">
      <div className="flex items-center gap-3">
        <ArrowUpCircle className="w-4 h-4 text-plutus-400 shrink-0" />

        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-200">
            <span className="font-medium text-plutus-300">
              v{updateInfo.latestVersion}
            </span>
            {updateInfo.releaseName &&
              updateInfo.releaseName !== `v${updateInfo.latestVersion}` && (
                <span className="text-gray-400"> — {updateInfo.releaseName}</span>
              )}
            <span className="text-gray-500 ml-1.5">
              (you're on v{updateInfo.currentVersion})
            </span>
          </p>

          {updateInfo.releaseNotes && (
            <button
              onClick={onToggleNotes}
              className="text-xs text-gray-500 hover:text-gray-300 mt-0.5 transition-colors"
            >
              {showNotes ? "Hide release notes" : "View release notes"}
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {updateInfo.releaseUrl && (
            <a
              href={updateInfo.releaseUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 text-gray-500 hover:text-gray-300 transition-colors"
              title="View on GitHub"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}

          <button
            onClick={onUpdate}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-plutus-600 hover:bg-plutus-500 text-white text-xs font-medium transition-all shadow-sm shadow-plutus-600/20"
          >
            <Download className="w-3 h-3" />
            Update now
          </button>

          <button
            onClick={onDismiss}
            className="p-1.5 text-gray-600 hover:text-gray-400 transition-colors"
            title="Dismiss"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {showNotes && updateInfo.releaseNotes && (
        <div className="mt-2 p-3 rounded-lg bg-gray-900/60 border border-gray-800/40 max-h-40 overflow-y-auto">
          <pre className="text-xs text-gray-400 whitespace-pre-wrap font-sans leading-relaxed">
            {updateInfo.releaseNotes}
          </pre>
        </div>
      )}
    </div>
  );
}

function InstallingBanner() {
  return (
    <div className="bg-plutus-500/5 border-b border-plutus-500/20 px-4 py-3 flex items-center gap-3">
      <Loader2 className="w-4 h-4 text-plutus-400 animate-spin shrink-0" />
      <p className="text-sm text-plutus-300">
        Installing update...
      </p>
    </div>
  );
}

function RestartingBanner({ newVersion }: { newVersion: string }) {
  const [dots, setDots] = useState("");

  // Animate dots
  useEffect(() => {
    const timer = setInterval(() => {
      setDots((d) => (d.length >= 3 ? "" : d + "."));
    }, 500);
    return () => clearInterval(timer);
  }, []);

  // Poll until the server comes back, then reload
  const poll = useCallback(async () => {
    const maxAttempts = 30; // ~30 seconds
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      try {
        const res = await fetch("/api/updates/check", { cache: "no-store" });
        if (res.ok) {
          // Server is back — reload the page to get the new UI
          window.location.reload();
          return;
        }
      } catch {
        // Server still down, keep polling
      }
    }
    // Fallback: just reload anyway
    window.location.reload();
  }, []);

  useEffect(() => {
    poll();
  }, [poll]);

  return (
    <div className="bg-plutus-500/5 border-b border-plutus-500/20 px-4 py-3 flex items-center gap-3">
      <Loader2 className="w-4 h-4 text-plutus-400 animate-spin shrink-0" />
      <p className="text-sm text-plutus-300">
        Updated to v{newVersion} — restarting{dots}
      </p>
    </div>
  );
}

function DoneBanner({
  newVersion,
  onClose,
}: {
  newVersion: string;
  onClose: () => void;
}) {
  return (
    <div className="bg-emerald-500/5 border-b border-emerald-500/20 px-4 py-3 flex items-center gap-3">
      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
      <p className="text-sm text-emerald-300 flex-1">
        Updated to v{newVersion}
      </p>
      <button
        onClick={onClose}
        className="p-1 text-gray-500 hover:text-gray-300 transition-colors"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

function ErrorBanner({
  message,
  onRetry,
  onClose,
}: {
  message: string;
  onRetry: () => void;
  onClose: () => void;
}) {
  return (
    <div className="bg-red-500/5 border-b border-red-500/20 px-4 py-3 flex items-center gap-3">
      <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
      <p className="text-sm text-red-300 flex-1">{message}</p>
      <button
        onClick={onRetry}
        className="text-xs text-gray-400 hover:text-gray-200 px-2 py-1 rounded-lg hover:bg-gray-800/60 transition-colors"
      >
        Retry
      </button>
      <button
        onClick={onClose}
        className="p-1 text-gray-500 hover:text-gray-300 transition-colors"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

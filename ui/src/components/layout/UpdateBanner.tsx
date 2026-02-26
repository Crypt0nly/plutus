import { useState } from "react";
import {
  Download,
  X,
  ArrowUpCircle,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAppStore } from "../../stores/appStore";

export function UpdateBanner() {
  const { updateInfo, setUpdateInfo } = useAppStore();
  const [updating, setUpdating] = useState(false);
  const [result, setResult] = useState<{
    success: boolean;
    message: string;
    restartRequired?: boolean;
  } | null>(null);
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
    setUpdating(true);
    setResult(null);
    try {
      const res = await api.applyUpdate();
      if (res.success) {
        setResult({
          success: true,
          message: `Updated to v${res.new_version || updateInfo.latestVersion}`,
          restartRequired: res.restart_required,
        });
      } else {
        setResult({
          success: false,
          message: res.error || "Update failed. Try updating manually.",
        });
      }
    } catch (e) {
      setResult({
        success: false,
        message: e instanceof Error ? e.message : "Update failed",
      });
    } finally {
      setUpdating(false);
    }
  };

  // Post-update result
  if (result) {
    return (
      <div
        className={`shrink-0 border-b px-4 py-3 flex items-center gap-3 ${
          result.success
            ? "bg-emerald-500/5 border-emerald-500/20"
            : "bg-red-500/5 border-red-500/20"
        }`}
      >
        {result.success ? (
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
        ) : (
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
        )}

        <p className={`text-sm flex-1 ${result.success ? "text-emerald-300" : "text-red-300"}`}>
          {result.message}
        </p>

        {result.restartRequired && result.success && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
            <RotateCcw className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-xs text-emerald-400 font-medium">Restart Plutus to finish</span>
          </div>
        )}

        {!result.success && (
          <button
            onClick={() => setResult(null)}
            className="text-xs text-gray-400 hover:text-gray-200 px-2 py-1 rounded-lg hover:bg-gray-800/60 transition-colors"
          >
            Retry
          </button>
        )}

        <button
          onClick={() => {
            setResult(null);
            setUpdateInfo({ ...updateInfo, dismissed: true });
          }}
          className="p-1 text-gray-500 hover:text-gray-300 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="shrink-0 bg-plutus-500/5 border-b border-plutus-500/20 px-4 py-2.5">
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

          {/* Expandable release notes */}
          {updateInfo.releaseNotes && (
            <button
              onClick={() => setShowNotes(!showNotes)}
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
            onClick={handleUpdate}
            disabled={updating}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-plutus-600 hover:bg-plutus-500 disabled:opacity-50 text-white text-xs font-medium transition-all shadow-sm shadow-plutus-600/20"
          >
            {updating ? (
              <>
                <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Updating...
              </>
            ) : (
              <>
                <Download className="w-3 h-3" />
                Update now
              </>
            )}
          </button>

          <button
            onClick={handleDismiss}
            className="p-1.5 text-gray-600 hover:text-gray-400 transition-colors"
            title="Dismiss"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Release notes expanded */}
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

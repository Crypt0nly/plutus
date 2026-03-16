import { useEffect, useState, useCallback } from "react";
import {
  Send,
  Mail,
  MessageCircle,
  MessageSquare,
  Plug,
  Unplug,
  CheckCircle2,
  XCircle,
  Loader2,
  Trash2,
  Play,
  Square,
  Zap,
  ExternalLink,
  Eye,
  EyeOff,
  Radio,
  Phone,
  X,
  ArrowRight,
  Settings2,
  Power,
  Brain,
  Sparkles,
  Wand2,
  Server,
  KeyRound,
  Globe,
  Shield,
  Calendar,
  HardDrive,
  Plus,
  Link,
  ChevronDown,
  ChevronUp,
  Rocket,
  Upload,
} from "lucide-react";
import { api } from "../../lib/api";

interface ConnectorField {
  name: string;
  label: string;
  type: "text" | "password" | "number";
  required: boolean;
  placeholder: string;
  help: string;
}

interface ConnectorData {
  name: string;
  display_name: string;
  description: string;
  icon: string;
  category: string;
  configured: boolean;
  connected: boolean;
  auto_start: boolean;
  config: Record<string, any>;
  config_schema: ConnectorField[];
  features?: string[];
  docs_url?: string;
  auth_type?: string;
}

const ICON_MAP: Record<string, React.ElementType> = {
  Send: Send,
  Mail: Mail,
  MessageCircle: MessageCircle,
  MessageSquare: MessageSquare,
  Brain: Brain,
  Sparkles: Sparkles,
  Wand2: Wand2,
  Server: Server,
  Calendar: Calendar,
  HardDrive: HardDrive,
  Globe: Globe,
  Rocket: Rocket,
  Upload: Upload,
};

/* ─── AI Provider Card ─── */
function AIProviderCard({
  connector,
  onConfigure,
}: {
  connector: ConnectorData;
  onConfigure: (c: ConnectorData) => void;
}) {
  const Icon = ICON_MAP[connector.icon] || Brain;

  return (
    <div
      className="group relative rounded-2xl transition-all duration-200"
      style={connector.configured ? { background: "rgba(168, 85, 247, 0.04)", border: "1px solid rgba(168, 85, 247, 0.2)" } : { background: "rgba(15, 18, 30, 0.8)", border: "1px solid rgba(255, 255, 255, 0.06)" }}
    >
      <div className="p-5 flex flex-col h-full">
        {/* Header row */}
        <div className="flex items-start justify-between mb-3">
          <div
            className="w-11 h-11 rounded-xl flex items-center justify-center transition-colors"
          style={connector.configured ? { background: "rgba(168, 85, 247, 0.12)", color: "#c084fc" } : { background: "rgba(255,255,255,0.05)", color: "#6b7280" }}
          >
            <Icon className="w-5 h-5" />
          </div>

          {connector.configured ? (
            <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-violet-400" style={{ background: "rgba(168, 85, 247, 0.1)", border: "1px solid rgba(168, 85, 247, 0.2)" }}>
              <KeyRound className="w-3 h-3" />
              Active
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-gray-500" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}>
              <Power className="w-3 h-3" />
              No key
            </span>
          )}
        </div>

        {/* Name + Description */}
        <h3 className="text-[15px] font-semibold text-gray-100 mb-1">
          {connector.display_name}
        </h3>
        <p className="text-xs text-gray-500 leading-relaxed line-clamp-2 mb-3">
          {connector.description}
        </p>

        {/* Feature tags */}
        {connector.features && connector.features.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {connector.features.map((feat) => (
              <span
                key={feat}
                className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-gray-800/60 text-gray-500 ring-1 ring-gray-700/20"
              >
                {feat}
              </span>
            ))}
          </div>
        )}

        {/* Action button */}
        <button
          onClick={() => onConfigure(connector)}
          className={`mt-auto w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
            connector.configured
              ? "text-gray-300 hover:text-gray-100"
              : "text-white active:scale-[0.98]"
          }`}
          style={connector.configured ? { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)" } : { background: "rgba(168, 85, 247, 0.8)", boxShadow: "0 4px 14px rgba(168, 85, 247, 0.2)" }}
        >
          {connector.configured ? (
            <>
              <Settings2 className="w-4 h-4" />
              Manage Key
            </>
          ) : (
            <>
              Add Key
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </div>
    </div>
  );
}

/* ─── Web Hosting Card ─── */
function HostingConnectorCard({
  connector,
  onConfigure,
}: {
  connector: ConnectorData;
  onConfigure: (c: ConnectorData) => void;
}) {
  const Icon = ICON_MAP[connector.icon] || Rocket;
  const isVercel = connector.name === "vercel";
  // Vercel: black/white brand feel → use indigo accent
  // Netlify: teal brand → use teal/emerald accent
  const accentRgb = isVercel ? "99, 102, 241" : "20, 184, 166";
  const accentText = isVercel ? "text-indigo-400" : "text-teal-400";
  const accentBg = isVercel ? "rgba(99,102,241,0.12)" : "rgba(20,184,166,0.12)";
  const accentBorder = isVercel ? "rgba(99,102,241,0.25)" : "rgba(20,184,166,0.25)";
  const btnBg = isVercel ? "rgba(99,102,241,0.85)" : "rgba(20,184,166,0.85)";
  const btnShadow = isVercel ? "0 4px 14px rgba(99,102,241,0.25)" : "0 4px 14px rgba(20,184,166,0.25)";
  const pillText = isVercel ? "text-indigo-400" : "text-teal-400";
  const pillBg = isVercel ? "rgba(99,102,241,0.1)" : "rgba(20,184,166,0.1)";
  const pillBorder = isVercel ? "rgba(99,102,241,0.2)" : "rgba(20,184,166,0.2)";

  return (
    <div
      className="group relative rounded-2xl transition-all duration-200"
      style={
        connector.configured
          ? { background: `rgba(${accentRgb}, 0.04)`, border: `1px solid rgba(${accentRgb}, 0.2)` }
          : { background: "rgba(15, 18, 30, 0.8)", border: "1px solid rgba(255, 255, 255, 0.06)" }
      }
    >
      <div className="p-5 flex flex-col h-full">
        {/* Header row */}
        <div className="flex items-start justify-between mb-3">
          <div
            className="w-11 h-11 rounded-xl flex items-center justify-center transition-colors"
            style={
              connector.configured
                ? { background: accentBg, color: isVercel ? "#818cf8" : "#2dd4bf" }
                : { background: "rgba(255,255,255,0.05)", color: "#6b7280" }
            }
          >
            <Icon className="w-5 h-5" />
          </div>

          {connector.configured ? (
            <span
              className={`flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full ${pillText}`}
              style={{ background: pillBg, border: `1px solid ${pillBorder}` }}
            >
              <CheckCircle2 className="w-3 h-3" />
              Ready
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-gray-500" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}>
              <Power className="w-3 h-3" />
              No token
            </span>
          )}
        </div>

        {/* Name + Description */}
        <h3 className="text-[15px] font-semibold text-gray-100 mb-1">
          {connector.display_name}
        </h3>
        <p className="text-xs text-gray-500 leading-relaxed line-clamp-2 mb-3">
          {connector.description}
        </p>

        {/* Feature tags */}
        {connector.features && connector.features.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {connector.features.slice(0, 4).map((feat) => (
              <span
                key={feat}
                className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-gray-800/60 text-gray-500 ring-1 ring-gray-700/20"
              >
                {feat}
              </span>
            ))}
            {connector.features.length > 4 && (
              <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-gray-800/60 text-gray-500 ring-1 ring-gray-700/20">
                +{connector.features.length - 4} more
              </span>
            )}
          </div>
        )}

        {/* Action button */}
        <button
          onClick={() => onConfigure(connector)}
          className={`mt-auto w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
            connector.configured
              ? "text-gray-300 hover:text-gray-100"
              : "text-white active:scale-[0.98]"
          }`}
          style={
            connector.configured
              ? { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)" }
              : { background: btnBg, boxShadow: btnShadow }
          }
        >
          {connector.configured ? (
            <>
              <Settings2 className="w-4 h-4" />
              Manage Token
            </>
          ) : (
            <>
              Connect
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </div>
    </div>
  );
}

/* ─── Messaging Connector Card ─── */
function ConnectorCard({
  connector,
  onConfigure,
}: {
  connector: ConnectorData;
  onConfigure: (c: ConnectorData) => void;
}) {
  const Icon = ICON_MAP[connector.icon] || Plug;
  const isListening =
    (connector.name === "telegram" || connector.name === "discord") && connector.configured && connector.connected;

  return (
    <div
      className="group relative rounded-2xl transition-all duration-200"
      style={connector.configured
        ? isListening
          ? { background: "rgba(59, 130, 246, 0.04)", border: "1px solid rgba(59, 130, 246, 0.2)" }
          : { background: "rgba(16, 185, 129, 0.04)", border: "1px solid rgba(16, 185, 129, 0.2)" }
        : { background: "rgba(15, 18, 30, 0.8)", border: "1px solid rgba(255, 255, 255, 0.06)" }
      }
    >
      <div className="p-5 flex flex-col h-full">
        {/* Icon + Status */}
        <div className="flex items-start justify-between mb-3">
          <div
            className="w-11 h-11 rounded-xl flex items-center justify-center transition-colors"
          style={isListening
            ? { background: "rgba(59, 130, 246, 0.12)", color: "#60a5fa" }
            : connector.configured
            ? { background: "rgba(16, 185, 129, 0.12)", color: "#34d399" }
            : { background: "rgba(255,255,255,0.05)", color: "#6b7280" }
          }
          >
            <Icon className="w-5 h-5" />
          </div>

          {/* Status pill */}
          {isListening ? (
            <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-blue-400" style={{ background: "rgba(59, 130, 246, 0.1)", border: "1px solid rgba(59, 130, 246, 0.2)" }}>
              <Radio className="w-3 h-3 animate-pulse" />
              Listening
            </span>
          ) : connector.configured ? (
            <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-emerald-400" style={{ background: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.2)" }}>
              <CheckCircle2 className="w-3 h-3" />
              Connected
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-gray-500" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}>
              <Power className="w-3 h-3" />
              Not configured
            </span>
          )}
        </div>

        {/* Name + Description */}
        <h3 className="text-[15px] font-semibold text-gray-100 mb-1">
          {connector.display_name}
        </h3>
        <p className="text-xs text-gray-500 leading-relaxed line-clamp-2 mb-4">
          {connector.description}
        </p>

        {/* Action button */}
        <button
          onClick={() => onConfigure(connector)}
          className={`mt-auto w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
            connector.configured
              ? "text-gray-300 hover:text-gray-100"
              : "text-white active:scale-[0.98]"
          }`}
          style={connector.configured ? { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)" } : { background: "rgba(99, 102, 241, 0.8)", boxShadow: "0 4px 14px rgba(99, 102, 241, 0.2)" }}
        >
          {connector.configured ? (
            <>
              <Settings2 className="w-4 h-4" />
              Manage
            </>
          ) : (
            <>
              Configure
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </div>
    </div>
  );
}

/* ─── Google Workspace Card ─── */
function GoogleConnectorCard({
  connector,
  onConfigure,
}: {
  connector: ConnectorData;
  onConfigure: (c: ConnectorData) => void;
}) {
  const Icon = ICON_MAP[connector.icon] || Globe;

  return (
    <div
      className="group relative rounded-2xl transition-all duration-200"
      style={connector.configured ? { background: "rgba(14, 165, 233, 0.04)", border: "1px solid rgba(14, 165, 233, 0.2)" } : { background: "rgba(15, 18, 30, 0.8)", border: "1px solid rgba(255, 255, 255, 0.06)" }}
    >
      <div className="p-5 flex flex-col h-full">
        {/* Header row */}
        <div className="flex items-start justify-between mb-3">
          <div
            className="w-11 h-11 rounded-xl flex items-center justify-center transition-colors"
          style={connector.configured ? { background: "rgba(14, 165, 233, 0.12)", color: "#38bdf8" } : { background: "rgba(255,255,255,0.05)", color: "#6b7280" }}
          >
            <Icon className="w-5 h-5" />
          </div>

          {connector.configured ? (
            <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-sky-400" style={{ background: "rgba(14, 165, 233, 0.1)", border: "1px solid rgba(14, 165, 233, 0.2)" }}>
              <Shield className="w-3 h-3" />
              Authorized
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full text-gray-500" style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}>
              <Power className="w-3 h-3" />
              Not connected
            </span>
          )}
        </div>

        {/* Name + Description */}
        <h3 className="text-[15px] font-semibold text-gray-100 mb-1">
          {connector.display_name}
        </h3>
        <p className="text-xs text-gray-500 leading-relaxed line-clamp-2 mb-3">
          {connector.description}
        </p>

        {/* Feature tags */}
        {connector.features && connector.features.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {connector.features.map((feat) => (
              <span
                key={feat}
              className="text-[10px] font-medium px-2 py-0.5 rounded-md text-gray-500"
              style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}
              >
                {feat}
              </span>
            ))}
          </div>
        )}

        {/* Action button */}
        <button
          onClick={() => onConfigure(connector)}
          className={`mt-auto w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
            connector.configured
              ? "text-gray-300 hover:text-gray-100"
              : "text-white active:scale-[0.98]"
          }`}
          style={connector.configured ? { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)" } : { background: "rgba(14, 165, 233, 0.8)", boxShadow: "0 4px 14px rgba(14, 165, 233, 0.2)" }}
        >
          {connector.configured ? (
            <>
              <Settings2 className="w-4 h-4" />
              Manage
            </>
          ) : (
            <>
              Connect
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </div>
    </div>
  );
}

/* ─── Configuration Modal ─── */
function ConfigureModal({
  connector,
  onClose,
  onRefresh,
}: {
  connector: ConnectorData;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [testMessage, setTestMessage] = useState("");
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>(
    {}
  );
  const [disconnecting, setDisconnecting] = useState(false);
  const [listening, setListening] = useState(false);
  const [togglingListener, setTogglingListener] = useState(false);
  const [autoStart, setAutoStart] = useState(connector.auto_start || false);
  const [togglingAutoStart, setTogglingAutoStart] = useState(false);

  const [authorizing, setAuthorizing] = useState(false);

  const Icon = ICON_MAP[connector.icon] || Plug;
  const isAI = connector.category === "ai";
  const isGoogle = connector.auth_type === "oauth";
  const isHosting = connector.category === "hosting";
  const supportsTwoWay = connector.name === "telegram" || connector.name === "discord";

  // Initialize form data
  useEffect(() => {
    const initial: Record<string, string> = {};
    (connector.config_schema ?? []).forEach((field) => {
      initial[field.name] = (connector.config ?? {})[field.name] || "";
    });
    setFormData(initial);
  }, [connector]);

  // Poll bridge status
  useEffect(() => {
    if (!supportsTwoWay || !connector.configured) return;

    const checkStatus = async () => {
      try {
        const status = await api.getBridgeStatus(connector.name);
        setListening(status.listening || false);
        if (status.auto_start !== undefined) {
          setAutoStart(status.auto_start);
        }
      } catch {
        // ignore
      }
    };

    checkStatus();
    const interval = setInterval(checkStatus, 5000);
    return () => clearInterval(interval);
  }, [connector.name, connector.configured, supportsTwoWay]);

  // Close on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const handleSave = async () => {
    setSaving(true);
    setTestResult(null);
    try {
      await api.updateConnectorConfig(connector.name, formData);
      onRefresh();
      setTestResult({ success: true, message: "Configuration saved!" });
      setTimeout(() => setTestResult(null), 3000);
    } catch (e: any) {
      setTestResult({
        success: false,
        message: `Failed to save: ${e.message}`,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.testConnector(connector.name);
      setTestResult({ success: result.success, message: result.message });
      if (result.success) onRefresh();
    } catch (e: any) {
      setTestResult({ success: false, message: `Test failed: ${e.message}` });
    } finally {
      setTesting(false);
    }
  };

  const handleSendTest = async () => {
    if (!testMessage.trim()) return;
    setSending(true);
    setSendResult(null);
    try {
      const result = await api.sendConnectorMessage(
        connector.name,
        testMessage
      );
      setSendResult({ success: result.success, message: result.message });
      if (result.success) setTestMessage("");
    } catch (e: any) {
      setSendResult({ success: false, message: `Send failed: ${e.message}` });
    } finally {
      setSending(false);
    }
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      if (listening) {
        await api.stopConnector(connector.name);
        setListening(false);
      }
      await api.disconnectConnector(connector.name);
      onRefresh();
      onClose();
    } catch (e: any) {
      console.error("Disconnect failed:", e);
    } finally {
      setDisconnecting(false);
    }
  };

  const togglePassword = (fieldName: string) => {
    setShowPasswords((prev) => ({ ...prev, [fieldName]: !prev[fieldName] }));
  };

  const toggleListener = async () => {
    setTogglingListener(true);
    try {
      if (listening) {
        await api.stopConnector(connector.name);
        setListening(false);
      } else {
        const result = await api.startConnector(connector.name);
        setListening(result.listening || false);
      }
    } catch (e: any) {
      console.error("Toggle listener failed:", e);
    } finally {
      setTogglingListener(false);
    }
  };

  const toggleAutoStart = async () => {
    setTogglingAutoStart(true);
    try {
      const newValue = !autoStart;
      await api.setConnectorAutoStart(connector.name, newValue);
      setAutoStart(newValue);
    } catch (e: any) {
      console.error("Toggle auto-start failed:", e);
    } finally {
      setTogglingAutoStart(false);
    }
  };

  // Color scheme based on category
  const accentColor = isGoogle ? "sky" : isAI ? "violet" : isHosting ? "indigo" : "plutus";
  const saveButtonClass = isGoogle
    ? "bg-sky-600 hover:bg-sky-500 shadow-md shadow-sky-600/15"
    : isAI
    ? "bg-violet-600 hover:bg-violet-500 shadow-md shadow-violet-600/15"
    : isHosting
    ? "bg-indigo-600 hover:bg-indigo-500 shadow-md shadow-indigo-600/15"
    : "bg-plutus-600 hover:bg-plutus-500 shadow-md shadow-plutus-600/15";

  const handleAuthorize = async () => {
    setAuthorizing(true);
    setTestResult(null);
    try {
      const result = await api.authorizeConnector(connector.name);
      setTestResult({ success: result.success, message: result.message });
      if (result.success) onRefresh();
    } catch (e: any) {
      setTestResult({
        success: false,
        message: `Authorization failed: ${e.message}`,
      });
    } finally {
      setAuthorizing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-4 max-h-[85vh] flex flex-col rounded-2xl shadow-2xl animate-fade-in" style={{ background: "rgba(10, 12, 22, 0.98)", border: "1px solid rgba(255, 255, 255, 0.08)", boxShadow: "0 25px 60px rgba(0, 0, 0, 0.6)" }}>
        {/* Modal header */}
        <div className="flex items-center gap-4 px-6 pt-6 pb-4" style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.06)" }}>
          <div
            className={`w-11 h-11 rounded-xl flex items-center justify-center ${
              isGoogle
                ? connector.configured
                  ? "bg-sky-500/15 text-sky-400"
                  : "bg-sky-500/10 text-sky-400"
                : isAI
                ? connector.configured
                  ? "bg-violet-500/15 text-violet-400"
                  : "bg-violet-500/10 text-violet-400"
                : isHosting
                ? connector.configured
                  ? "bg-indigo-500/15 text-indigo-400"
                  : "bg-indigo-500/10 text-indigo-400"
                : listening
                ? "bg-blue-500/15 text-blue-400"
                : connector.configured
                ? "bg-emerald-500/15 text-emerald-400"
                : "bg-plutus-500/10 text-plutus-400"
            }`}
          >
            <Icon className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-gray-100">
                {connector.display_name}
              </h3>
              {isAI && (
                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400 ring-1 ring-violet-500/20 uppercase tracking-wider">
                  AI
                </span>
              )}
              {isGoogle && (
                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400 ring-1 ring-sky-500/20 uppercase tracking-wider">
                  OAuth
                </span>
              )}
              {isHosting && (
                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 ring-1 ring-indigo-500/20 uppercase tracking-wider">
                  Hosting
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500 truncate">
              {connector.description}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-gray-500 hover:text-gray-300 transition-colors"
            style={{ background: "transparent" }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,0.06)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* AI Provider features */}
          {isAI && connector.features && connector.features.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {connector.features.map((feat) => (
                <span
                  key={feat}
                  className="text-[10px] font-medium px-2.5 py-1 rounded-lg bg-violet-500/8 text-violet-300/70 ring-1 ring-violet-500/15"
                >
                  {feat}
                </span>
              ))}
            </div>
          )}

          {/* Two-Way Messaging (Telegram/Discord) */}
          {supportsTwoWay && connector.configured && (
              <div className="rounded-xl p-4 space-y-3" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className="w-9 h-9 rounded-xl flex items-center justify-center"
                    style={listening ? { background: "rgba(59, 130, 246, 0.12)", color: "#60a5fa" } : { background: "rgba(255,255,255,0.05)", color: "#6b7280" }}
                  >
                    <Phone className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-gray-200">
                      Two-Way Messaging
                    </h4>
                    <p className="text-[11px] text-gray-500 mt-0.5">
                      {listening
                        ? "Listening for incoming messages"
                        : "Chat with Plutus from Telegram"}
                    </p>
                  </div>
                </div>
                <button
                  onClick={toggleListener}
                  disabled={togglingListener}
                  className={`flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all disabled:opacity-50 ${
                    listening
                      ? "bg-red-500/10 hover:bg-red-500/20 text-red-400 ring-1 ring-red-500/20"
                      : "bg-blue-600 hover:bg-blue-500 text-white"
                  }`}
                >
                  {togglingListener ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : listening ? (
                    <Square className="w-3 h-3" />
                  ) : (
                    <Play className="w-3 h-3" />
                  )}
                  {listening ? "Stop" : "Start"}
                </button>
              </div>

              {listening && (
                <div className="flex items-center gap-2 text-[11px] text-blue-400/70 pl-12">
                  <Radio className="w-3 h-3 animate-pulse" />
                  Messages sent to the bot will be processed automatically
                </div>
              )}

              {/* Auto-start */}
              <div className="flex items-center justify-between pt-3" style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                <div>
                  <p className="text-xs font-medium text-gray-300">
                    Start on launch
                  </p>
                  <p className="text-[10px] text-gray-600 mt-0.5">
                    Auto-start when Plutus boots
                  </p>
                </div>
                <button
                  onClick={toggleAutoStart}
                  disabled={togglingAutoStart}
                  className={`toggle-switch ${togglingAutoStart ? 'opacity-50' : ''}`}
                  data-state={autoStart ? 'on' : 'off'}
                  role="switch"
                  aria-checked={autoStart}
                >
                  <span className="toggle-thumb" />
                </button>
              </div>
            </div>
          )}

          {/* Configuration Fields */}
          <div>
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              {isGoogle ? "OAuth Setup" : isAI ? "API Key" : isHosting ? "Deploy Token" : "Configuration"}
            </h4>
            <div className="space-y-3">
              {(connector.config_schema ?? []).map((field) => {
                const hasSaved = (connector.config ?? {})[`_has_${field.name}`] === true;
                const currentVal = formData[field.name] || "";
                const effectivePlaceholder =
                  hasSaved && !currentVal
                    ? `${field.label} saved — enter new value to replace`
                    : field.placeholder;

                return (
                <div key={field.name}>
                  <label className="text-xs font-medium text-gray-400 mb-1.5 block">
                    {field.label}
                    {field.required && !hasSaved && (
                      <span className="text-red-400 ml-0.5">*</span>
                    )}
                    {hasSaved && !currentVal && (
                      <span className="text-emerald-400 ml-1.5 text-[10px] font-normal">Saved</span>
                    )}
                  </label>
                  <div className="relative">
                    <input
                      type={
                        field.type === "password" && !showPasswords[field.name]
                          ? "password"
                          : field.type === "number"
                          ? "number"
                          : "text"
                      }
                      className={`w-full bg-gray-900/80 border border-gray-800/60 rounded-xl px-3.5 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none transition-all ${
                          isGoogle
                          ? "focus:border-sky-500/50 focus:ring-1 focus:ring-sky-500/20"
                          : isAI
                          ? "focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/20"
                          : isHosting
                          ? "focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/20"
                          : "focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20"
                      }`}
                      placeholder={effectivePlaceholder}
                      value={currentVal}
                      onChange={(e) =>
                        setFormData((prev) => ({
                          ...prev,
                          [field.name]: e.target.value,
                        }))
                      }
                    />
                    {field.type === "password" && currentVal && (
                      <button
                        type="button"
                        onClick={() => togglePassword(field.name)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400 transition-colors"
                      >
                        {showPasswords[field.name] ? (
                          <EyeOff className="w-4 h-4" />
                        ) : (
                          <Eye className="w-4 h-4" />
                        )}
                      </button>
                    )}
                  </div>
                  {field.help && (
                    <p className="text-[10px] text-gray-600 mt-1.5 pl-0.5">
                      {field.help}
                    </p>
                  )}
                </div>
                );
              })}
            </div>
          </div>

          {/* OAuth Authorize button for Google connectors */}
          {isGoogle && (
            <div className="rounded-xl bg-gray-900/80 border border-gray-800/40 p-4 space-y-3">
              <div className="flex items-center gap-3">
                <div
                  className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                    connector.configured
                      ? "bg-sky-500/15 text-sky-400"
                      : "bg-gray-800 text-gray-500"
                  }`}
                >
                  <Shield className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <h4 className="text-sm font-semibold text-gray-200">
                    Google Authorization
                  </h4>
                  <p className="text-[11px] text-gray-500 mt-0.5">
                    {connector.configured
                      ? "Account is authorized via OAuth"
                      : connector.config._has_client_id
                        ? "Credentials saved — click below to authorize"
                        : "Save your Client ID first, then authorize"}
                  </p>
                </div>
              </div>
              <button
                onClick={handleAuthorize}
                disabled={authorizing || !(formData.client_id?.trim() || connector.config._has_client_id)}
                className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-50 ${
                  connector.configured
                    ? "bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 ring-1 ring-sky-500/20"
                    : "bg-sky-600 hover:bg-sky-500 text-white"
                }`}
              >
                {authorizing ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Shield className="w-4 h-4" />
                )}
                {connector.configured ? "Re-authorize" : "Authorize with Google"}
              </button>
              <p className="text-[10px] text-gray-600 text-center">
                Opens Google's consent screen in your browser — tokens stay local
              </p>
            </div>
          )}

          {/* Hosting: Test Token + docs link */}
          {isHosting && (
            <div className="rounded-xl p-4 space-y-3" style={{ background: "rgba(99,102,241,0.04)", border: "1px solid rgba(99,102,241,0.12)" }}>
              <div className="flex items-center gap-3">
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                  connector.configured ? "bg-indigo-500/15 text-indigo-400" : "bg-gray-800 text-gray-500"
                }`}>
                  <Rocket className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <h4 className="text-sm font-semibold text-gray-200">Token Verification</h4>
                  <p className="text-[11px] text-gray-500 mt-0.5">
                    {connector.configured
                      ? "Token saved — click to verify it's still valid"
                      : "Save your token above, then verify it works"}
                  </p>
                </div>
              </div>
              <button
                onClick={handleTest}
                disabled={testing || (!formData.token?.trim() && !connector.configured)}
                className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-50 ${
                  connector.configured
                    ? "bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 ring-1 ring-indigo-500/20"
                    : "bg-indigo-600 hover:bg-indigo-500 text-white"
                }`}
              >
                {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                {connector.configured ? "Re-verify Token" : "Verify Token"}
              </button>
              {connector.docs_url && (
                <a
                  href={connector.docs_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center gap-1.5 text-[11px] text-indigo-400/60 hover:text-indigo-400 transition-colors"
                >
                  <ExternalLink className="w-3 h-3" />
                  Get your {connector.display_name} token
                </a>
              )}
            </div>
          )}

          {/* Docs link for AI providers */}
          {isAI && connector.docs_url && (
            <a
              href={connector.docs_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-xs text-violet-400/70 hover:text-violet-400 transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Get your API key from {connector.display_name}
            </a>
          )}

          {/* Test Result */}
          {testResult && (
            <div
              className={`flex items-start gap-2.5 p-3.5 rounded-xl text-sm ${
                testResult.success
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  : "bg-red-500/10 text-red-400 border border-red-500/20"
              }`}
            >
              {testResult.success ? (
                <CheckCircle2 className="w-4 h-4 mt-0.5 flex-shrink-0" />
              ) : (
                <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              )}
              <span>{testResult.message}</span>
            </div>
          )}

          {/* Send Test Message (messaging connectors only) */}
          {!isAI && !isHosting && connector.configured && connector.name !== "whatsapp" && (
            <div>
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                Send Test Message
              </h4>
              <div className="flex gap-2">
                <input
                  type="text"
                  className="flex-1 bg-gray-900/80 border border-gray-800/60 rounded-xl px-3.5 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20 transition-all"
                  placeholder={`Message via ${connector.display_name}...`}
                  value={testMessage}
                  onChange={(e) => setTestMessage(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSendTest()}
                />
                <button
                  onClick={handleSendTest}
                  disabled={sending || !testMessage.trim()}
                  className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
                >
                  {sending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>
              {sendResult && (
                <div
                  className={`flex items-center gap-2 mt-2 text-xs ${
                    sendResult.success ? "text-emerald-400" : "text-red-400"
                  }`}
                >
                  {sendResult.success ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5" />
                  )}
                  <span>{sendResult.message}</span>
                </div>
              )}
            </div>
          )}

          {/* Telegram bot link */}
          {connector.name === "telegram" && connector.config.bot_username && (
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <ExternalLink className="w-3.5 h-3.5" />
              <span>
                Bot:{" "}
                <a
                  href={`https://t.me/${connector.config.bot_username?.replace("@", "")}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-plutus-400 hover:text-plutus-300 transition-colors"
                >
                  {connector.config.bot_username}
                </a>
              </span>
            </div>
          )}
        </div>

        {/* Modal footer */}
        <div className="flex items-center gap-2 px-6 py-4" style={{ borderTop: "1px solid rgba(255, 255, 255, 0.06)" }}>
          <button
            onClick={handleSave}
            disabled={saving}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-white text-sm font-medium transition-all disabled:opacity-50 active:scale-[0.98] ${saveButtonClass}`}
          >
            {saving ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : isAI ? (
              <KeyRound className="w-3.5 h-3.5" />
            ) : (
              <Plug className="w-3.5 h-3.5" />
            )}
            Save
          </button>
          <button
            onClick={handleTest}
            disabled={testing}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gray-800/80 hover:bg-gray-800 text-gray-300 hover:text-gray-100 text-sm font-medium transition-all disabled:opacity-50"
          >
            {testing ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Zap className="w-3.5 h-3.5" />
            )}
            Test Connection
          </button>
          <div className="flex-1" />
          {connector.configured && (
            <button
              onClick={handleDisconnect}
              disabled={disconnecting}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-red-500/10 hover:bg-red-500/20 text-red-400 text-sm font-medium transition-all disabled:opacity-50 ring-1 ring-red-500/20"
            >
              {disconnecting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Trash2 className="w-3.5 h-3.5" />
              )}
              {isAI ? "Remove Key" : "Disconnect"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Main View ─── */
export default function ConnectorsView() {
  const [connectors, setConnectors] = useState<ConnectorData[]>([]);
  const [loading, setLoading] = useState(true);
  const [configuring, setConfiguring] = useState<ConnectorData | null>(null);
  const [showAddCustom, setShowAddCustom] = useState(false);
  const [customForm, setCustomForm] = useState({
    connector_id: "",
    display_name: "",
    description: "",
    base_url: "",
    auth_type: "none",
  });
  const [customCredentials, setCustomCredentials] = useState<Record<string, string>>({});
  const [customHeaders, setCustomHeaders] = useState("");
  const [creatingCustom, setCreatingCustom] = useState(false);
  const [customError, setCustomError] = useState("");
  const [customSuccess, setCustomSuccess] = useState("");

  const handleCreateCustom = async () => {
    setCreatingCustom(true);
    setCustomError("");
    setCustomSuccess("");
    try {
      let parsedHeaders: Record<string, string> = {};
      if (customHeaders.trim()) {
        try {
          parsedHeaders = JSON.parse(customHeaders);
        } catch {
          setCustomError("Invalid JSON in default headers");
          setCreatingCustom(false);
          return;
        }
      }
      await api.createCustomConnector({
        connector_id: customForm.connector_id,
        display_name: customForm.display_name,
        description: customForm.description,
        base_url: customForm.base_url,
        auth_type: customForm.auth_type,
        credentials: Object.keys(customCredentials).length > 0 ? customCredentials : undefined,
        default_headers: Object.keys(parsedHeaders).length > 0 ? parsedHeaders : undefined,
      });
      setCustomSuccess(`Connector "${customForm.display_name || customForm.connector_id}" created!`);
      setCustomForm({ connector_id: "", display_name: "", description: "", base_url: "", auth_type: "none" });
      setCustomCredentials({});
      setCustomHeaders("");
      fetchConnectors();
      setTimeout(() => {
        setCustomSuccess("");
        setShowAddCustom(false);
      }, 2000);
    } catch (e: any) {
      setCustomError(e.message || "Failed to create connector");
    } finally {
      setCreatingCustom(false);
    }
  };

  const fetchConnectors = useCallback(async () => {
    try {
      const data = await api.getConnectors();
      setConnectors(data.connectors || []);
    } catch (e) {
      console.error("Failed to load connectors:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConnectors();
  }, [fetchConnectors]);

  const handleRefresh = useCallback(() => {
    fetchConnectors();
    // Update the configuring connector if it's open
    if (configuring) {
      api
        .getConnector(configuring.name)
        .then((updated) => setConfiguring(updated as ConnectorData))
        .catch(() => {});
    }
  }, [fetchConnectors, configuring]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-plutus-500/30 border-t-plutus-500 rounded-full animate-spin" />
          <p className="text-sm text-gray-500">Loading connectors...</p>
        </div>
      </div>
    );
  }

  // Split by category
  const aiConnectors = connectors.filter((c) => c.category === "ai");
  const googleConnectors = connectors.filter((c) => c.category === "google");
  const hostingConnectors = connectors.filter((c) => c.category === "hosting");
  const customConnectors = connectors.filter((c) => (c as any).is_custom);
  const messagingConnectors = connectors.filter(
    (c) => c.category !== "ai" && c.category !== "google" && c.category !== "hosting" && !(c as any).is_custom
  );

  const aiConfigured = aiConnectors.filter((c) => c.configured);
  const aiAvailable = aiConnectors.filter((c) => !c.configured);

  const googleConfigured = googleConnectors.filter((c) => c.configured);
  const googleAvailable = googleConnectors.filter((c) => !c.configured);

  const hostingConfigured = hostingConnectors.filter((c) => c.configured);
  const hostingAvailable = hostingConnectors.filter((c) => !c.configured);

  const msgConfigured = messagingConnectors.filter((c) => c.configured);
  const msgAvailable = messagingConnectors.filter((c) => !c.configured);

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto p-6 space-y-10">
        {/* Header */}
        <div>
          <h2 className="text-xl font-bold text-gray-100 mb-1">Connections</h2>
          <p className="text-sm text-gray-500">
            Manage AI provider keys and messaging integrations in one place
          </p>
        </div>

        {/* ═══════════════════════════════════════════════ */}
        {/* AI PROVIDERS SECTION                           */}
        {/* ═══════════════════════════════════════════════ */}
        {aiConnectors.length > 0 && (
          <div>
            {/* Section header */}
            <div className="flex items-center gap-3 mb-5">
              <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: "rgba(168, 85, 247, 0.08)", border: "1px solid rgba(168, 85, 247, 0.12)" }}>
                <Brain className="w-4 h-4 text-violet-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-200">
                  AI Providers
                </h3>
                <p className="text-[11px] text-gray-500">
                  API keys for language models, image &amp; video generation
                </p>
              </div>
              {aiConfigured.length > 0 && (
                <span className="ml-auto text-[10px] font-semibold px-2.5 py-1 rounded-full text-violet-400" style={{ background: "rgba(168, 85, 247, 0.08)", border: "1px solid rgba(168, 85, 247, 0.15)" }}>
                  {aiConfigured.length} active
                </span>
              )}
            </div>

            {/* AI cards grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Show configured first, then unconfigured */}
              {[...aiConfigured, ...aiAvailable].map((c) => (
                <AIProviderCard
                  key={c.name}
                  connector={c}
                  onConfigure={setConfiguring}
                />
              ))}
            </div>
          </div>
        )}

        {/* Divider */}
        {aiConnectors.length > 0 && (googleConnectors.length > 0 || messagingConnectors.length > 0) && (
          <div className="h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.06), transparent)" }} />
        )}

        {/* ═══════════════════════════════════════════════ */}
        {/* GOOGLE WORKSPACE SECTION                       */}
        {/* ═══════════════════════════════════════════════ */}
        {googleConnectors.length > 0 && (
          <div>
            {/* Section header */}
            <div className="flex items-center gap-3 mb-5">
              <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: "rgba(14, 165, 233, 0.08)", border: "1px solid rgba(14, 165, 233, 0.12)" }}>
                <Shield className="w-4 h-4 text-sky-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-200">
                  Google Workspace
                </h3>
                <p className="text-[11px] text-gray-500">
                  Gmail, Calendar &amp; Drive — authorized via OAuth (no secrets stored)
                </p>
              </div>
              {googleConfigured.length > 0 && (
                <span className="ml-auto text-[10px] font-semibold px-2.5 py-1 rounded-full text-sky-400" style={{ background: "rgba(14, 165, 233, 0.08)", border: "1px solid rgba(14, 165, 233, 0.15)" }}>
                  {googleConfigured.length} authorized
                </span>
              )}
            </div>

            {/* Google cards grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[...googleConfigured, ...googleAvailable].map((c) => (
                <GoogleConnectorCard
                  key={c.name}
                  connector={c}
                  onConfigure={setConfiguring}
                />
              ))}
            </div>
          </div>
        )}

        {/* Divider */}
        {(aiConnectors.length > 0 || googleConnectors.length > 0) && hostingConnectors.length > 0 && (
          <div className="h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.06), transparent)" }} />
        )}

        {/* ═══════════════════════════════════════════════ */}
        {/* WEB HOSTING SECTION                             */}
        {/* ═══════════════════════════════════════════════ */}
        {hostingConnectors.length > 0 && (
          <div>
            {/* Section header */}
            <div className="flex items-center gap-3 mb-5">
              <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: "rgba(99, 102, 241, 0.08)", border: "1px solid rgba(99, 102, 241, 0.12)" }}>
                <Rocket className="w-4 h-4 text-indigo-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-200">
                  Web Hosting
                </h3>
                <p className="text-[11px] text-gray-500">
                  Deploy and host websites publicly — React, Next.js, Vue, static HTML &amp; more
                </p>
              </div>
              {hostingConfigured.length > 0 && (
                <span className="ml-auto text-[10px] font-semibold px-2.5 py-1 rounded-full text-indigo-400" style={{ background: "rgba(99, 102, 241, 0.08)", border: "1px solid rgba(99, 102, 241, 0.15)" }}>
                  {hostingConfigured.length} connected
                </span>
              )}
            </div>

            {/* Hosting cards grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[...hostingConfigured, ...hostingAvailable].map((c) => (
                <HostingConnectorCard
                  key={c.name}
                  connector={c}
                  onConfigure={setConfiguring}
                />
              ))}
            </div>
          </div>
        )}

        {/* Divider */}
        {(aiConnectors.length > 0 || googleConnectors.length > 0 || hostingConnectors.length > 0) && messagingConnectors.length > 0 && (
          <div className="h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.06), transparent)" }} />
        )}

        {/* ═══════════════════════════════════════════════ */}
        {/* MESSAGING CONNECTORS SECTION                   */}
        {/* ═══════════════════════════════════════════════ */}
        {messagingConnectors.length > 0 && (
          <div>
            {/* Section header */}
            <div className="flex items-center gap-3 mb-5">
              <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: "rgba(99, 102, 241, 0.08)", border: "1px solid rgba(99, 102, 241, 0.12)" }}>
                <Globe className="w-4 h-4 text-plutus-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-gray-200">
                  Messaging &amp; Notifications
                </h3>
                <p className="text-[11px] text-gray-500">
                  Send messages and enable two-way communication
                </p>
              </div>
              {msgConfigured.length > 0 && (
                <span className="ml-auto text-[10px] font-semibold px-2.5 py-1 rounded-full text-emerald-400" style={{ background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.15)" }}>
                  {msgConfigured.length} connected
                </span>
              )}
            </div>

            {/* Messaging cards grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Show configured first, then unconfigured */}
              {[...msgConfigured, ...msgAvailable].map((c) => (
                <ConnectorCard
                  key={c.name}
                  connector={c}
                  onConfigure={setConfiguring}
                />
              ))}
            </div>
          </div>
        )}

        {/* Empty state */}
        {connectors.length === 0 && (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
              <Plug className="w-7 h-7 text-gray-600" />
            </div>
            <h3 className="text-sm font-semibold text-gray-300 mb-1">
              No connections available
            </h3>
            <p className="text-xs text-gray-500 max-w-sm mx-auto">
              Connections let Plutus access AI providers and communicate through
              external services.
            </p>
          </div>
        )}

        {/* ═══════════════════════════════════════════════ */}
        {/* CUSTOM API CONNECTORS SECTION                   */}
        {/* ═══════════════════════════════════════════════ */}
        <div>
           <div className="h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.06), transparent)" }} />

          {/* Section header */}
          <div className="flex items-center gap-3 mb-5">
            <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: "rgba(245, 158, 11, 0.08)", border: "1px solid rgba(245, 158, 11, 0.12)" }}>
              <Link className="w-4 h-4 text-amber-400" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-200">
                Custom API Connectors
              </h3>
              <p className="text-[11px] text-gray-500">
                Connect any REST API — Jira, Notion, Slack, or your own services
              </p>
            </div>
            {customConnectors.length > 0 && (
              <span className="ml-auto text-[10px] font-semibold px-2.5 py-1 rounded-full text-amber-400" style={{ background: "rgba(245, 158, 11, 0.08)", border: "1px solid rgba(245, 158, 11, 0.15)" }}>
                {customConnectors.length} custom
              </span>
            )}
          </div>

          {/* Existing custom connectors */}
          {customConnectors.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
              {customConnectors.map((c) => (
                <ConnectorCard
                  key={c.name}
                  connector={c}
                  onConfigure={setConfiguring}
                />
              ))}
            </div>
          )}

          {/* Add Custom Connector button / form */}
          <button
            onClick={() => setShowAddCustom(!showAddCustom)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 text-gray-300 hover:text-gray-100"
            style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)" }}
          >
            {showAddCustom ? (
              <>
                <ChevronUp className="w-4 h-4" />
                Hide
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                Add Custom Connector
              </>
            )}
          </button>

          {showAddCustom && (
            <div className="mt-4 rounded-2xl p-6 space-y-4" style={{ background: "rgba(15, 18, 30, 0.8)", border: "1px solid rgba(255, 255, 255, 0.06)" }}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Connector ID */}
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">Connector ID *</label>
                  <input
                    type="text"
                    value={customForm.connector_id}
                    onChange={(e) => setCustomForm({ ...customForm, connector_id: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })}
                    placeholder="jira, notion, slack..."
                    className="w-full px-3 py-2.5 rounded-xl bg-gray-900/60 border border-gray-700/50 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-colors"
                  />
                </div>

                {/* Display Name */}
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">Display Name</label>
                  <input
                    type="text"
                    value={customForm.display_name}
                    onChange={(e) => setCustomForm({ ...customForm, display_name: e.target.value })}
                    placeholder="My Jira Instance"
                    className="w-full px-3 py-2.5 rounded-xl bg-gray-900/60 border border-gray-700/50 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-colors"
                  />
                </div>

                {/* Base URL */}
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">Base URL *</label>
                  <input
                    type="text"
                    value={customForm.base_url}
                    onChange={(e) => setCustomForm({ ...customForm, base_url: e.target.value })}
                    placeholder="https://api.example.com/v1"
                    className="w-full px-3 py-2.5 rounded-xl bg-gray-900/60 border border-gray-700/50 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-colors"
                  />
                </div>

                {/* Auth Type */}
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">Authentication</label>
                  <select
                    value={customForm.auth_type}
                    onChange={(e) => {
                      setCustomForm({ ...customForm, auth_type: e.target.value });
                      setCustomCredentials({});
                    }}
                    className="w-full px-3 py-2.5 rounded-xl bg-gray-900/60 border border-gray-700/50 text-sm text-gray-200 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-colors appearance-none"
                  >
                    <option value="none">None</option>
                    <option value="api_key">API Key</option>
                    <option value="bearer_token">Bearer Token</option>
                    <option value="basic_auth">Basic Auth</option>
                  </select>
                </div>
              </div>

              {/* Auth credentials based on type */}
              {customForm.auth_type === "api_key" && (
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">API Key</label>
                  <input
                    type="password"
                    value={customCredentials.api_key || ""}
                    onChange={(e) => setCustomCredentials({ ...customCredentials, api_key: e.target.value })}
                    placeholder="Your API key"
                    className="w-full px-3 py-2.5 rounded-xl bg-gray-900/60 border border-gray-700/50 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-colors"
                  />
                  <p className="text-[10px] text-gray-600 mt-1">Sent as X-API-Key header</p>
                </div>
              )}

              {customForm.auth_type === "bearer_token" && (
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1.5">Bearer Token</label>
                  <input
                    type="password"
                    value={customCredentials.token || ""}
                    onChange={(e) => setCustomCredentials({ ...customCredentials, token: e.target.value })}
                    placeholder="Your bearer token"
                    className="w-full px-3 py-2.5 rounded-xl bg-gray-900/60 border border-gray-700/50 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-colors"
                  />
                </div>
              )}

              {customForm.auth_type === "basic_auth" && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1.5">Username</label>
                    <input
                      type="text"
                      value={customCredentials.username || ""}
                      onChange={(e) => setCustomCredentials({ ...customCredentials, username: e.target.value })}
                      placeholder="Username"
                      className="w-full px-3 py-2.5 rounded-xl bg-gray-900/60 border border-gray-700/50 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-colors"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1.5">Password</label>
                    <input
                      type="password"
                      value={customCredentials.password || ""}
                      onChange={(e) => setCustomCredentials({ ...customCredentials, password: e.target.value })}
                      placeholder="Password or token"
                      className="w-full px-3 py-2.5 rounded-xl bg-gray-900/60 border border-gray-700/50 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-colors"
                    />
                  </div>
                </div>
              )}

              {/* Description */}
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">Description</label>
                <input
                  type="text"
                  value={customForm.description}
                  onChange={(e) => setCustomForm({ ...customForm, description: e.target.value })}
                  placeholder="What does this API do?"
                  className="w-full px-3 py-2.5 rounded-xl bg-gray-900/60 border border-gray-700/50 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-colors"
                />
              </div>

              {/* Default Headers */}
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">Default Headers (optional JSON)</label>
                <input
                  type="text"
                  value={customHeaders}
                  onChange={(e) => setCustomHeaders(e.target.value)}
                  placeholder='{"Accept": "application/json"}'
                  className="w-full px-3 py-2.5 rounded-xl bg-gray-900/60 border border-gray-700/50 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/20 transition-colors font-mono text-xs"
                />
              </div>

              {/* Error / Success */}
              {customError && (
                <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/10 px-3 py-2 rounded-lg">
                  <XCircle className="w-3.5 h-3.5 flex-shrink-0" />
                  {customError}
                </div>
              )}
              {customSuccess && (
                <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-500/10 px-3 py-2 rounded-lg">
                  <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                  {customSuccess}
                </div>
              )}

              {/* Create button */}
              <div className="flex justify-end">
                <button
                  onClick={handleCreateCustom}
                  disabled={creatingCustom || !customForm.connector_id || !customForm.base_url}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 bg-amber-500/90 hover:bg-amber-500 text-gray-900 shadow-md shadow-amber-500/15 hover:shadow-lg hover:shadow-amber-500/20 active:scale-[0.98] disabled:opacity-40 disabled:pointer-events-none"
                >
                  {creatingCustom ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Plus className="w-4 h-4" />
                  )}
                  Create Connector
                </button>
              </div>
            </div>
          )}
        </div>

        {/* How it works */}
        <div className="rounded-2xl p-5" style={{ background: "rgba(15, 18, 30, 0.8)", border: "1px solid rgba(255, 255, 255, 0.06)" }}>
          <h4 className="text-sm font-semibold text-gray-300 mb-4">How It Works</h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { step: "1", text: "Add your AI provider API keys to unlock models and generation tools" },
              { step: "2", text: "Configure messaging connectors for notifications and two-way chat" },
              { step: "3", text: 'Test each connection to verify it works — hit "Test Connection"' },
              { step: "4", text: 'Ask Plutus to "generate an image" or "send me a Telegram message"' },
            ].map((item) => (
              <div key={item.step} className="flex items-start gap-3 p-3 rounded-xl" style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)" }}>
                <span className="w-6 h-6 rounded-lg text-plutus-400 text-xs font-bold flex items-center justify-center flex-shrink-0" style={{ background: "rgba(99, 102, 241, 0.1)", border: "1px solid rgba(99, 102, 241, 0.15)" }}>
                  {item.step}
                </span>
                <span className="text-xs text-gray-500 leading-relaxed">{item.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Configuration Modal */}
      {configuring && (
        <ConfigureModal
          connector={configuring}
          onClose={() => setConfiguring(null)}
          onRefresh={handleRefresh}
        />
      )}
    </div>
  );
}

import { useEffect, useState, useCallback } from "react";
import {
  Send,
  Mail,
  MessageCircle,
  Plug,
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
  configured: boolean;
  connected: boolean;
  auto_start: boolean;
  config: Record<string, any>;
  config_schema: ConnectorField[];
}

const ICON_MAP: Record<string, React.ElementType> = {
  Send: Send,
  Mail: Mail,
  MessageCircle: MessageCircle,
};

/* ─── Connector Card (grid item) ─── */
function ConnectorCard({
  connector,
  onConfigure,
}: {
  connector: ConnectorData;
  onConfigure: (c: ConnectorData) => void;
}) {
  const Icon = ICON_MAP[connector.icon] || Plug;
  const isListening =
    connector.name === "telegram" && connector.configured && connector.connected;

  return (
    <div
      className={`group relative rounded-2xl border transition-all duration-200 hover:shadow-lg ${
        connector.configured
          ? isListening
            ? "border-blue-500/25 bg-blue-500/[0.03] hover:border-blue-500/40 hover:shadow-blue-500/5"
            : "border-emerald-500/25 bg-emerald-500/[0.03] hover:border-emerald-500/40 hover:shadow-emerald-500/5"
          : "border-gray-800/60 bg-surface hover:border-gray-700/80 hover:shadow-gray-900/20"
      }`}
    >
      <div className="p-5">
        {/* Icon + Status */}
        <div className="flex items-start justify-between mb-4">
          <div
            className={`w-12 h-12 rounded-xl flex items-center justify-center transition-colors ${
              isListening
                ? "bg-blue-500/15 text-blue-400"
                : connector.configured
                ? "bg-emerald-500/15 text-emerald-400"
                : "bg-gray-800/80 text-gray-500 group-hover:bg-gray-800 group-hover:text-gray-400"
            }`}
          >
            <Icon className="w-6 h-6" />
          </div>

          {/* Status pill */}
          {isListening ? (
            <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full bg-blue-500/15 text-blue-400 ring-1 ring-blue-500/20">
              <Radio className="w-3 h-3 animate-pulse" />
              Listening
            </span>
          ) : connector.configured ? (
            <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/20">
              <CheckCircle2 className="w-3 h-3" />
              Connected
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-[10px] font-semibold px-2.5 py-1 rounded-full bg-gray-800/60 text-gray-500 ring-1 ring-gray-700/30">
              <Power className="w-3 h-3" />
              Not configured
            </span>
          )}
        </div>

        {/* Name + Description */}
        <h3 className="text-[15px] font-semibold text-gray-100 mb-1">
          {connector.display_name}
        </h3>
        <p className="text-xs text-gray-500 leading-relaxed line-clamp-2 mb-5">
          {connector.description}
        </p>

        {/* Action button */}
        <button
          onClick={() => onConfigure(connector)}
          className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
            connector.configured
              ? "bg-gray-800/60 hover:bg-gray-800 text-gray-300 hover:text-gray-100"
              : "bg-plutus-600 hover:bg-plutus-500 text-white shadow-md shadow-plutus-600/15 hover:shadow-lg hover:shadow-plutus-500/20 active:scale-[0.98]"
          }`}
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

  const Icon = ICON_MAP[connector.icon] || Plug;
  const supportsTwoWay = connector.name === "telegram";

  // Initialize form data
  useEffect(() => {
    const initial: Record<string, string> = {};
    connector.config_schema.forEach((field) => {
      initial[field.name] = connector.config[field.name] || "";
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-4 max-h-[85vh] flex flex-col bg-gray-950 border border-gray-800/60 rounded-2xl shadow-2xl shadow-black/40 animate-fade-in">
        {/* Modal header */}
        <div className="flex items-center gap-4 px-6 pt-6 pb-4 border-b border-gray-800/40">
          <div
            className={`w-11 h-11 rounded-xl flex items-center justify-center ${
              listening
                ? "bg-blue-500/15 text-blue-400"
                : connector.configured
                ? "bg-emerald-500/15 text-emerald-400"
                : "bg-plutus-500/10 text-plutus-400"
            }`}
          >
            <Icon className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-gray-100">
              {connector.display_name}
            </h3>
            <p className="text-xs text-gray-500 truncate">
              {connector.description}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-gray-500 hover:text-gray-300 hover:bg-gray-800/60 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* Two-Way Messaging (Telegram) */}
          {supportsTwoWay && connector.configured && (
            <div className="rounded-xl bg-gray-900/80 border border-gray-800/40 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                      listening
                        ? "bg-blue-500/15 text-blue-400"
                        : "bg-gray-800 text-gray-500"
                    }`}
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
              <div className="flex items-center justify-between pt-3 border-t border-gray-800/30">
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
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    autoStart ? "bg-blue-600" : "bg-gray-700"
                  } ${togglingAutoStart ? "opacity-50" : ""}`}
                >
                  <span
                    className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                      autoStart ? "translate-x-[18px]" : "translate-x-[3px]"
                    }`}
                  />
                </button>
              </div>
            </div>
          )}

          {/* Configuration Fields */}
          <div>
            <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Configuration
            </h4>
            <div className="space-y-3">
              {connector.config_schema.map((field) => (
                <div key={field.name}>
                  <label className="text-xs font-medium text-gray-400 mb-1.5 block">
                    {field.label}
                    {field.required && (
                      <span className="text-red-400 ml-0.5">*</span>
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
                      className="w-full bg-gray-900/80 border border-gray-800/60 rounded-xl px-3.5 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20 transition-all"
                      placeholder={field.placeholder}
                      value={formData[field.name] || ""}
                      onChange={(e) =>
                        setFormData((prev) => ({
                          ...prev,
                          [field.name]: e.target.value,
                        }))
                      }
                    />
                    {field.type === "password" && (
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
              ))}
            </div>
          </div>

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

          {/* Send Test Message */}
          {connector.configured && connector.name !== "whatsapp" && (
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
        <div className="flex items-center gap-2 px-6 py-4 border-t border-gray-800/40">
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-plutus-600 hover:bg-plutus-500 text-white text-sm font-medium transition-all disabled:opacity-50 shadow-md shadow-plutus-600/15 active:scale-[0.98]"
          >
            {saving ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
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
              Disconnect
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

  const configured = connectors.filter((c) => c.configured);
  const available = connectors.filter((c) => !c.configured);

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto p-6 space-y-8">
        {/* Header */}
        <div>
          <h2 className="text-xl font-bold text-gray-100 mb-1">Connectors</h2>
          <p className="text-sm text-gray-500">
            Link Plutus with external services for notifications and two-way
            communication
          </p>
        </div>

        {/* Connected */}
        {configured.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-4">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Connected
              </h3>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20">
                {configured.length}
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {configured.map((c) => (
                <ConnectorCard
                  key={c.name}
                  connector={c}
                  onConfigure={setConfiguring}
                />
              ))}
            </div>
          </div>
        )}

        {/* Available */}
        {available.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-4">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Available
              </h3>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-gray-800/60 text-gray-500 ring-1 ring-gray-700/30">
                {available.length}
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {available.map((c) => (
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
            <div className="w-14 h-14 rounded-2xl bg-gray-800/60 flex items-center justify-center mx-auto mb-4">
              <Plug className="w-7 h-7 text-gray-600" />
            </div>
            <h3 className="text-sm font-semibold text-gray-300 mb-1">
              No connectors available
            </h3>
            <p className="text-xs text-gray-500 max-w-sm mx-auto">
              Connectors let Plutus communicate through external services like
              Telegram, email, and more.
            </p>
          </div>
        )}

        {/* How it works */}
        <div className="rounded-2xl bg-surface border border-gray-800/60 p-5">
          <h4 className="text-sm font-semibold text-gray-300 mb-3">
            How Connectors Work
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {[
              {
                step: "1",
                text: "Click a connector and enter your credentials",
              },
              {
                step: "2",
                text: 'Hit "Test Connection" to verify it works',
              },
              {
                step: "3",
                text: "Enable two-way messaging to chat from external apps",
              },
              {
                step: "4",
                text: 'Ask Plutus to "send me a Telegram message" anytime',
              },
            ].map((item) => (
              <div
                key={item.step}
                className="flex items-start gap-3 p-3 rounded-xl bg-gray-900/40"
              >
                <span className="w-6 h-6 rounded-lg bg-plutus-500/10 text-plutus-400 text-xs font-bold flex items-center justify-center flex-shrink-0">
                  {item.step}
                </span>
                <span className="text-xs text-gray-500 leading-relaxed">
                  {item.text}
                </span>
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

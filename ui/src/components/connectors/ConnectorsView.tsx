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

function ConnectorCard({
  connector,
  onRefresh,
}: {
  connector: ConnectorData;
  onRefresh: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
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

  // Initialize form data from existing config
  useEffect(() => {
    const initial: Record<string, string> = {};
    connector.config_schema.forEach((field) => {
      initial[field.name] = connector.config[field.name] || "";
    });
    setFormData(initial);
  }, [connector]);

  // Poll bridge status for two-way connectors
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
      setTestResult({
        success: result.success,
        message: result.message,
      });
      if (result.success) {
        onRefresh();
      }
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
      setSendResult({
        success: result.success,
        message: result.message,
      });
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
    <div
      className={`rounded-xl border transition-all ${
        connector.configured
          ? listening
            ? "border-blue-500/30 bg-gray-900/80"
            : "border-emerald-500/30 bg-gray-900/80"
          : "border-gray-700/50 bg-gray-900/50"
      }`}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-4 p-5 text-left hover:bg-gray-800/30 rounded-xl transition-colors"
      >
        <div
          className={`w-12 h-12 rounded-xl flex items-center justify-center ${
            listening
              ? "bg-blue-500/15 text-blue-400"
              : connector.configured
              ? "bg-emerald-500/15 text-emerald-400"
              : "bg-gray-800 text-gray-500"
          }`}
        >
          <Icon className="w-6 h-6" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-gray-100">
              {connector.display_name}
            </h3>
            {listening && (
              <span className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400">
                <Radio className="w-3 h-3 animate-pulse" />
                Listening
              </span>
            )}
            {connector.configured && !listening && (
              <span className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400">
                <CheckCircle2 className="w-3 h-3" />
                Connected
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500 mt-0.5">
            {listening
              ? "Two-way messaging active — chat with Plutus via " +
                connector.display_name
              : connector.description}
          </p>
        </div>
        <div
          className={`w-5 h-5 text-gray-500 transition-transform ${
            expanded ? "rotate-180" : ""
          }`}
        >
          <svg viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        </div>
      </button>

      {/* Expanded Content */}
      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-gray-800/50 pt-4">
          {/* Two-Way Messaging Toggle (for Telegram) */}
          {supportsTwoWay && connector.configured && (
            <div className="rounded-lg bg-gray-800/50 border border-gray-700/30 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      listening
                        ? "bg-blue-500/15 text-blue-400"
                        : "bg-gray-700/50 text-gray-500"
                    }`}
                  >
                    <Phone className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-gray-200">
                      Two-Way Messaging
                    </h4>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {listening
                        ? "Plutus is listening for your Telegram messages and will respond"
                        : "Enable to chat with Plutus directly from Telegram"}
                    </p>
                  </div>
                </div>
                <button
                  onClick={toggleListener}
                  disabled={togglingListener}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${
                    listening
                      ? "bg-red-900/30 hover:bg-red-900/50 text-red-400"
                      : "bg-blue-600 hover:bg-blue-500 text-white"
                  }`}
                >
                  {togglingListener ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : listening ? (
                    <Square className="w-3.5 h-3.5" />
                  ) : (
                    <Play className="w-3.5 h-3.5" />
                  )}
                  {listening ? "Stop" : "Start"}
                </button>
              </div>
              {listening && (
                <div className="mt-3 flex items-center gap-2 text-xs text-blue-400/70">
                  <Radio className="w-3 h-3 animate-pulse" />
                  <span>
                    Messages you send to the bot will be processed by Plutus and
                    replied to automatically
                  </span>
                </div>
              )}

              {/* Auto-start toggle */}
              <div className="mt-3 flex items-center justify-between pt-3 border-t border-gray-700/30">
                <div>
                  <h5 className="text-xs font-medium text-gray-300">
                    Start on launch
                  </h5>
                  <p className="text-[11px] text-gray-600 mt-0.5">
                    Automatically start two-way messaging when Plutus starts
                  </p>
                </div>
                <button
                  onClick={toggleAutoStart}
                  disabled={togglingAutoStart}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    autoStart
                      ? "bg-blue-600"
                      : "bg-gray-700"
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

          {/* Config Form */}
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
                    className="w-full bg-gray-800/80 border border-gray-700/50 rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20 transition-colors"
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
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors"
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
                  <p className="text-[11px] text-gray-600 mt-1">{field.help}</p>
                )}
              </div>
            ))}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2 pt-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-plutus-600 hover:bg-plutus-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
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
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm font-medium transition-colors disabled:opacity-50"
            >
              {testing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Zap className="w-3.5 h-3.5" />
              )}
              Test Connection
            </button>
            {connector.configured && (
              <button
                onClick={handleDisconnect}
                disabled={disconnecting}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-red-900/30 hover:bg-red-900/50 text-red-400 text-sm font-medium transition-colors disabled:opacity-50 ml-auto"
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

          {/* Test Result */}
          {testResult && (
            <div
              className={`flex items-start gap-2 p-3 rounded-lg text-sm ${
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

          {/* Send Test Message (only for configured connectors) */}
          {connector.configured && connector.name !== "whatsapp" && (
            <div className="border-t border-gray-800/50 pt-4">
              <label className="text-xs font-medium text-gray-400 mb-1.5 block">
                Send Test Message
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  className="flex-1 bg-gray-800/80 border border-gray-700/50 rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-plutus-500/50 focus:ring-1 focus:ring-plutus-500/20 transition-colors"
                  placeholder={`Send a test message via ${connector.display_name}...`}
                  value={testMessage}
                  onChange={(e) => setTestMessage(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSendTest()}
                />
                <button
                  onClick={handleSendTest}
                  disabled={sending || !testMessage.trim()}
                  className="flex items-center gap-1.5 px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
                >
                  {sending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                  Send
                </button>
              </div>
              {sendResult && (
                <div
                  className={`flex items-center gap-2 mt-2 text-sm ${
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

          {/* Telegram-specific: link to bot */}
          {connector.name === "telegram" && connector.config.bot_username && (
            <div className="flex items-center gap-2 text-sm text-gray-500">
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
      )}
    </div>
  );
}

export default function ConnectorsView() {
  const [connectors, setConnectors] = useState<ConnectorData[]>([]);
  const [loading, setLoading] = useState(true);

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

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-gray-500 animate-spin" />
      </div>
    );
  }

  const configured = connectors.filter((c) => c.configured);
  const available = connectors.filter((c) => !c.configured);

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-gray-100 mb-1 flex items-center gap-2">
          <Plug className="w-5 h-5 text-plutus-400" />
          Connectors
        </h2>
        <p className="text-sm text-gray-500">
          Link Plutus with external services for two-way communication —
          chat with Plutus from Telegram, get email notifications, and more
        </p>
      </div>

      {/* Connected Services */}
      {configured.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Connected ({configured.length})
          </h3>
          <div className="space-y-3">
            {configured.map((c) => (
              <ConnectorCard
                key={c.name}
                connector={c}
                onRefresh={fetchConnectors}
              />
            ))}
          </div>
        </div>
      )}

      {/* Available Services */}
      {available.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Available ({available.length})
          </h3>
          <div className="space-y-3">
            {available.map((c) => (
              <ConnectorCard
                key={c.name}
                connector={c}
                onRefresh={fetchConnectors}
              />
            ))}
          </div>
        </div>
      )}

      {/* Info Box */}
      <div className="rounded-xl bg-gray-800/30 border border-gray-700/30 p-4">
        <h4 className="text-sm font-semibold text-gray-300 mb-2">
          How Connectors Work
        </h4>
        <ul className="text-sm text-gray-500 space-y-1.5">
          <li className="flex items-start gap-2">
            <span className="text-plutus-400 mt-0.5">1.</span>
            <span>
              Configure a connector by entering your credentials above
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-plutus-400 mt-0.5">2.</span>
            <span>Click "Test Connection" to verify everything works</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-plutus-400 mt-0.5">3.</span>
            <span>
              Click "Start" to enable two-way messaging — Plutus will listen
              for your messages and respond automatically
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-plutus-400 mt-0.5">4.</span>
            <span>
              You can also ask Plutus in the chat to "send me a Telegram message"
              or use connectors in skills and automations
            </span>
          </li>
        </ul>
      </div>
    </div>
  );
}

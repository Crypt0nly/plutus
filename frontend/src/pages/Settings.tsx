import { useAuth, useUser } from '@clerk/clerk-react'
import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'

// ── Types ─────────────────────────────────────────────────────────────────────

type OS = 'macos' | 'linux' | 'windows' | 'unknown'

// ── Detect OS (best-effort from browser) ──────────────────────────────────────

function detectOS(): OS {
  const ua = navigator.userAgent.toLowerCase()
  if (ua.includes('mac os')) return 'macos'
  if (ua.includes('linux'))  return 'linux'
  if (ua.includes('win'))    return 'windows'
  return 'unknown'
}

const OS_LABELS: Record<OS, string> = {
  macos:   '🍎 macOS',
  linux:   '🐧 Linux',
  windows: '🪟 Windows',
  unknown: '❓ Unknown',
}

// ── Copy helper ───────────────────────────────────────────────────────────────

function useCopyToClipboard() {
  const [copied, setCopied] = useState(false)
  const copy = useCallback((text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [])
  return { copy, copied }
}

// ── BridgeInstallSection ──────────────────────────────────────────────────────

function BridgeInstallSection() {
  const { getToken } = useAuth()
  const [connected, setConnected]     = useState<boolean | null>(null)
  const [detectedOS, setDetectedOS]   = useState<OS>('unknown')
  const [selectedOS, setSelectedOS]   = useState<OS>('unknown')
  const [script, setScript]           = useState<string | null>(null)
  const [loadingScript, setLoadingScript] = useState(false)
  const [scriptError, setScriptError] = useState<string | null>(null)
  const { copy, copied } = useCopyToClipboard()

  // Detect OS once
  useEffect(() => {
    const os = detectOS()
    setDetectedOS(os)
    setSelectedOS(os)
  }, [])

  // Poll bridge status every 5 s
  const checkStatus = useCallback(async () => {
    try {
      const res = await api.getLocalBridgeStatus()
      setConnected(res.connected ?? false)
    } catch {
      setConnected(false)
    }
  }, [])

  useEffect(() => {
    checkStatus()
    const id = setInterval(checkStatus, 5000)
    return () => clearInterval(id)
  }, [checkStatus])

  // Load the install script for the selected OS
  const loadScript = useCallback(async (os: OS) => {
    if (os === 'unknown') return
    setLoadingScript(true)
    setScriptError(null)
    setScript(null)
    try {
      const token = await getToken()
      const raw = await api.getBridgeInstallScript(os, token ?? '')
      setScript(raw)
    } catch (err) {
      setScriptError('Failed to load install script. Make sure you're logged in.')
    } finally {
      setLoadingScript(false)
    }
  }, [getToken])

  const handleOSChange = (os: OS) => {
    setSelectedOS(os)
    setScript(null)
  }

  const statusColor =
    connected === null ? 'text-gray-500' :
    connected           ? 'text-emerald-400' :
    'text-amber-400'

  const statusText =
    connected === null ? 'Checking…' :
    connected           ? '🟢 Connected — Local PC is linked' :
    '🟡 Not connected — Bridge not running'

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            🔗 Local Bridge
          </h3>
          <p className="text-gray-400 text-sm mt-1">
            Connect your PC so Plutus can run commands, open apps, and access your
            local files — automatically, without any manual steps.
          </p>
        </div>
        <span className={`text-sm font-medium whitespace-nowrap ${statusColor}`}>
          {statusText}
        </span>
      </div>

      {/* Already connected */}
      {connected && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4">
          <p className="text-emerald-300 text-sm font-medium">
            ✅ Your PC is linked! Plutus will now prefer running tools locally and only fall
            back to the cloud sandbox when needed.
          </p>
          <p className="text-emerald-300/60 text-xs mt-2">
            The bridge service is registered as a system daemon and starts automatically on
            every login. You don't need to do anything.
          </p>
        </div>
      )}

      {/* How it works */}
      {!connected && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          {[
            { icon: '📥', title: 'One command', desc: 'Copy the install command below and paste it into your terminal.' },
            { icon: '⚙️', title: 'Auto-registered', desc: 'The bridge installs itself as a system service and starts immediately.' },
            { icon: '♾️', title: 'Always on', desc: 'Starts on every login, restarts on crash. Zero babysitting required.' },
          ].map(s => (
            <div key={s.title} className="bg-gray-800/60 border border-gray-700/50 rounded-lg p-3">
              <div className="text-xl mb-1">{s.icon}</div>
              <div className="font-medium text-gray-200">{s.title}</div>
              <div className="text-gray-500 text-xs mt-1">{s.desc}</div>
            </div>
          ))}
        </div>
      )}

      {/* OS Selector */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">Your OS:</span>
          {(['macos', 'linux', 'windows'] as OS[]).map(os => (
            <button
              key={os}
              onClick={() => handleOSChange(os)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                selectedOS === os
                  ? 'bg-indigo-600 text-white border border-indigo-500'
                  : 'bg-gray-800 text-gray-400 border border-gray-700 hover:border-gray-500'
              }`}
            >
              {OS_LABELS[os]}
              {os === detectedOS && (
                <span className="ml-1 text-[10px] opacity-60">(detected)</span>
              )}
            </button>
          ))}
        </div>

        {/* Generate script button */}
        {!script && (
          <button
            onClick={() => loadScript(selectedOS)}
            disabled={loadingScript || selectedOS === 'unknown'}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-all"
          >
            {loadingScript ? (
              <>
                <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Generating…
              </>
            ) : (
              '⬇️  Generate Install Command'
            )}
          </button>
        )}

        {scriptError && (
          <p className="text-red-400 text-sm">{scriptError}</p>
        )}

        {/* The install script */}
        {script && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400 font-medium">
                {selectedOS === 'windows' ? '📋 Paste in PowerShell / CMD:' : '📋 Paste in Terminal:'}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => copy(script)}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                    copied
                      ? 'bg-emerald-600 text-white border border-emerald-500'
                      : 'bg-gray-700 text-gray-300 border border-gray-600 hover:border-gray-400'
                  }`}
                >
                  {copied ? '✓ Copied!' : '📋 Copy'}
                </button>
                <button
                  onClick={() => setScript(null)}
                  className="px-3 py-1 rounded-lg text-xs text-gray-500 border border-gray-700 hover:border-gray-500 transition-all"
                >
                  ✕ Hide
                </button>
              </div>
            </div>
            <pre className="bg-gray-950 border border-gray-800 rounded-xl p-4 text-xs text-green-300 font-mono overflow-x-auto whitespace-pre max-h-72 overflow-y-auto">
              {script}
            </pre>
            <p className="text-gray-600 text-xs">
              The script downloads the bridge, installs Python deps, and registers a
              system service. Your session token is baked in automatically.
            </p>
          </div>
        )}
      </div>

      {/* Already installed but not connected */}
      {!connected && (
        <div className="bg-gray-800/40 border border-gray-700/50 rounded-xl p-4 space-y-2">
          <p className="text-gray-400 text-sm font-medium">Already installed? Check status:</p>
          <code className="block text-xs text-blue-300 font-mono bg-gray-950 rounded-lg px-3 py-2">
            python3 ~/.plutus/plutus_bridge.py --service-status
          </code>
          <p className="text-gray-500 text-xs">
            If it shows <span className="text-amber-300">installed-stopped</span>, run:
          </p>
          <code className="block text-xs text-blue-300 font-mono bg-gray-950 rounded-lg px-3 py-2">
            {detectedOS === 'linux'
              ? 'systemctl --user start ai.plutus.bridge'
              : detectedOS === 'macos'
              ? 'launchctl load -w ~/Library/LaunchAgents/ai.plutus.bridge.plist'
              : 'schtasks /Run /TN ai.plutus.bridge'}
          </code>
        </div>
      )}
    </div>
  )
}

// ── Main Settings Page ────────────────────────────────────────────────────────

export default function Settings() {
  const { userId } = useAuth()
  const { user } = useUser()

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold mb-6">Settings</h2>

      {/* Account */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h3 className="text-lg font-semibold mb-4">Account</h3>
        <div className="space-y-3 text-gray-400">
          <p>Email: {user?.primaryEmailAddress?.emailAddress}</p>
          <p>User ID: {userId}</p>
        </div>
      </div>

      {/* Agent Configuration */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h3 className="text-lg font-semibold mb-4">Agent Configuration</h3>
        <p className="text-gray-500">Agent settings will appear here once the backend is connected.</p>
      </div>

      {/* Local Bridge — fully automatic */}
      <BridgeInstallSection />
    </div>
  )
}
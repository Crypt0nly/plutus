import { useState } from 'react'
import { useAuth } from '@clerk/clerk-react'

export default function AgentChat() {
  const { getToken } = useAuth()
  const [messages, setMessages] = useState<Array<{role: string, content: string}>>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const userMsg = { role: 'user', content: input }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)
    try {
      const token = await getToken()
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: input }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.response }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error contacting agent.' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-73px)]">
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 mt-20">
            <p className="text-4xl mb-4">&#x1F4AC;</p>
            <p>Send a message to your Plutus agent</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-2xl px-4 py-3 rounded-xl ${msg.role === 'user' ? 'bg-amber-500/20 text-amber-100' : 'bg-gray-800 text-gray-200'}`}>
              {msg.content}
            </div>
          </div>
        ))}
        {loading && <div className="text-gray-500 animate-pulse">Agent is thinking...</div>}
      </div>
      <div className="border-t border-gray-800 p-4">
        <div className="flex gap-3 max-w-4xl mx-auto">
          <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && sendMessage()} placeholder="Message your agent..." className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-amber-500" />
          <button onClick={sendMessage} disabled={loading} className="px-6 py-3 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-black font-semibold rounded-lg transition">Send</button>
        </div>
      </div>
    </div>
  )
}

import { useAuth, useUser } from '@clerk/clerk-react'

export default function Settings() {
  const { userId } = useAuth()
  const { user } = useUser()
  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h2 className="text-2xl font-bold mb-6">Settings</h2>
      <div className="space-y-6">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h3 className="text-lg font-semibold mb-4">Account</h3>
          <div className="space-y-3 text-gray-400">
            <p>Email: {user?.primaryEmailAddress?.emailAddress}</p>
            <p>User ID: {userId}</p>
          </div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h3 className="text-lg font-semibold mb-4">Agent Configuration</h3>
          <p className="text-gray-500">Agent settings will appear here once the backend is connected.</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h3 className="text-lg font-semibold mb-4">Local Bridge</h3>
          <p className="text-gray-500">Download and install the local bridge daemon to connect your PC.</p>
          <button className="mt-4 px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-sm transition">Download Bridge</button>
        </div>
      </div>
    </div>
  )
}
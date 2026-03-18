export default function Dashboard() {
  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h2 className="text-2xl font-bold mb-6">Dashboard</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h3 className="text-sm text-gray-400 mb-2">Agent Status</h3>
          <p className="text-2xl font-bold text-green-400">Online</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h3 className="text-sm text-gray-400 mb-2">Tasks Today</h3>
          <p className="text-2xl font-bold">0</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h3 className="text-sm text-gray-400 mb-2">Local Bridge</h3>
          <p className="text-2xl font-bold text-gray-500">Not Connected</p>
        </div>
      </div>
      <div className="mt-8 bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h3 className="text-lg font-semibold mb-4">Recent Activity</h3>
        <p className="text-gray-500">No recent activity. Start chatting with your agent!</p>
      </div>
    </div>
  )
}
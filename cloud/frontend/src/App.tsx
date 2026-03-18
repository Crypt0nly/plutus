import { Show, UserButton, SignInButton } from '@clerk/clerk-react';
import { Link, Route, Routes } from 'react-router-dom';
import AgentChat from './pages/AgentChat';
import Connectors from './pages/Connectors';
import Dashboard from './pages/Dashboard';
import Memory from './pages/Memory';
import Settings from './pages/Settings';

function LandingPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-950 via-gray-900 to-gray-950 flex items-center justify-center text-white">
      <div className="text-center space-y-6">
        <h1 className="text-5xl font-bold text-amber-400">Plutus</h1>
        <p className="text-gray-400 text-lg">Your AI agent — running 24/7 in the cloud</p>
        <SignInButton mode="modal">
          <button className="px-6 py-3 bg-amber-500 hover:bg-amber-400 text-gray-950 font-semibold rounded-lg transition-colors">
            Sign In
          </button>
        </SignInButton>
      </div>
    </div>
  );
}

function AppLayout() {
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur px-6 py-3 flex items-center justify-between sticky top-0 z-50">
        <nav className="flex items-center gap-6 text-sm font-medium">
          <span className="text-amber-400 font-bold text-lg mr-2">⚡ Plutus</span>
          <Link to="/dashboard" className="text-gray-300 hover:text-amber-400 transition-colors">Dashboard</Link>
          <Link to="/chat" className="text-gray-300 hover:text-amber-400 transition-colors">Chat</Link>
          <Link to="/memory" className="text-gray-300 hover:text-amber-400 transition-colors">Memory</Link>
          <Link to="/connectors" className="text-gray-300 hover:text-amber-400 transition-colors">Connectors</Link>
          <Link to="/settings" className="text-gray-300 hover:text-amber-400 transition-colors">Settings</Link>
        </nav>
        <UserButton afterSignOutUrl="/" />
      </header>
      <main className="p-6 max-w-7xl mx-auto">
        <Routes>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/chat" element={<AgentChat />} />
          <Route path="/memory" element={<Memory />} />
          <Route path="/connectors" element={<Connectors />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Dashboard />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <>
      <Show when="signed-out"><LandingPage /></Show>
      <Show when="signed-in"><AppLayout /></Show>
    </>
  );
}

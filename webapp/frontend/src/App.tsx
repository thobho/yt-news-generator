import { Routes, Route } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import RunList from './components/RunList'
import RunDetail from './components/RunDetail'
import SettingsPage from './components/SettingsPage'
import Login from './components/Login'

function AppContent() {
  const { isAuthenticated, isAuthEnabled, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="container">
        <div className="loading">Loading...</div>
      </div>
    )
  }

  // Show login if auth is enabled and user is not authenticated
  if (isAuthEnabled && !isAuthenticated) {
    return <Login />
  }

  return (
    <div className="container">
      <Routes>
        <Route path="/" element={<RunList />} />
        <Route path="/runs/:runId" element={<RunDetail />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}

export default App

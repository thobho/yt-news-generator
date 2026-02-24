import { Routes, Route } from 'react-router-dom'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import Box from '@mui/material/Box'
import { AuthProvider, useAuth } from './context/AuthContext'
import { TenantProvider, useTenant } from './context/TenantContext'
import Navbar from './components/Navbar'
import RunList from './components/RunList'
import RunDetail from './components/RunDetail'
import NewRunPage from './components/NewRunPage'
import SettingsPage from './components/SettingsPage'
import AnalyticsPage from './components/AnalyticsPage'
import SchedulerPage from './pages/SchedulerPage'
import PromptEditorPage from './pages/PromptEditorPage'
import LogsPage from './pages/LogsPage'
import Login from './components/Login'

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#ffffff',
      paper: '#ffffff',
    },
  },
})

function AppContent() {
  const { isAuthenticated, isAuthEnabled, isLoading } = useAuth()
  const { loading: tenantLoading } = useTenant()

  if (isLoading || tenantLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        Loading...
      </Box>
    )
  }

  // Show login if auth is enabled and user is not authenticated
  if (isAuthEnabled && !isAuthenticated) {
    return <Login />
  }

  return (
    <Box>
      <Navbar />
      <Box sx={{ px: 3, pb: 3 }}>
        <Routes>
          <Route path="/" element={<RunList />} />
          <Route path="/new-run" element={<NewRunPage />} />
          <Route path="/runs/:runId" element={<RunDetail />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/prompts/:promptType/:promptId" element={<PromptEditorPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/scheduler" element={<SchedulerPage />} />
          <Route path="/logs" element={<LogsPage />} />
        </Routes>
      </Box>
    </Box>
  )
}

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <TenantProvider>
        <AuthProvider>
          <AppContent />
        </AuthProvider>
      </TenantProvider>
    </ThemeProvider>
  )
}

export default App

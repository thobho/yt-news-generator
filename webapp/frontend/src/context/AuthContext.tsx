import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { fetchAuthStatus, login as apiLogin, logout as apiLogout } from '../api/client'

interface AuthContextType {
  isAuthenticated: boolean
  isAuthEnabled: boolean
  isLoading: boolean
  error: string | null
  login: (password: string) => Promise<void>
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isAuthEnabled, setIsAuthEnabled] = useState(true)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const checkAuth = async () => {
    try {
      setIsLoading(true)
      setError(null)
      const status = await fetchAuthStatus()
      setIsAuthenticated(status.authenticated)
      setIsAuthEnabled(status.auth_enabled)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to check auth status')
      setIsAuthenticated(false)
    } finally {
      setIsLoading(false)
    }
  }

  const login = async (password: string) => {
    try {
      setError(null)
      await apiLogin(password)
      setIsAuthenticated(true)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Login failed'
      setError(message)
      throw err
    }
  }

  const logout = async () => {
    try {
      setError(null)
      await apiLogout()
      setIsAuthenticated(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Logout failed')
    }
  }

  useEffect(() => {
    checkAuth()
  }, [])

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        isAuthEnabled,
        isLoading,
        error,
        login,
        logout,
        checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

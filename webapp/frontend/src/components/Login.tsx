import { useState, FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const [password, setPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { login } = useAuth()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)

    try {
      await login(password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <h1>YT News Generator</h1>
        <p className="login-subtitle">Enter password to access the dashboard</p>

        <form onSubmit={handleSubmit}>
          <div className="login-field">
            <label htmlFor="password">Password</label>
            <input
              type="password"
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              autoFocus
              disabled={isSubmitting}
            />
          </div>

          {error && <div className="login-error">{error}</div>}

          <button
            type="submit"
            className="primary login-button"
            disabled={isSubmitting || !password}
          >
            {isSubmitting ? 'Logging in...' : 'Login'}
          </button>
        </form>
      </div>
    </div>
  )
}

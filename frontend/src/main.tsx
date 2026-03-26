import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import './app.css'

// Initialize dark mode from persisted store or default
const stored = localStorage.getItem('molabel-ui')
if (stored) {
  try {
    const parsed = JSON.parse(stored) as { state?: { theme?: string } }
    const theme = parsed.state?.theme
    document.documentElement.classList.toggle('dark', theme !== 'light')
  } catch {
    document.documentElement.classList.add('dark')
  }
} else {
  document.documentElement.classList.add('dark')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

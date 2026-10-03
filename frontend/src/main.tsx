import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { Toaster } from 'sonner'
import App from './App'
import { reportClientError } from './lib/api'
import { AuthProvider } from './lib/auth'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 10_000, refetchOnWindowFocus: false },
  },
})

window.addEventListener('error', (e) => reportClientError(e.message, { source: e.filename, line: e.lineno }))
window.addEventListener('unhandledrejection', (e) => reportClientError(String(e.reason)))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
          <Toaster
            theme="dark"
            position="bottom-right"
            toastOptions={{
              style: { background: '#14171c', border: '1px solid #232831', color: '#e8eaef' },
            }}
          />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)

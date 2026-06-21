import { Component, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

interface BoundaryProps {
  children: ReactNode
  /** When this changes, a caught error is cleared (e.g. on route change). */
  resetKey?: string
}
interface BoundaryState {
  error: Error | null
}

class Boundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error }
  }

  componentDidUpdate(prev: BoundaryProps) {
    // Navigating to a new route clears a previous page's crash.
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null })
    }
  }

  componentDidCatch(error: Error, info: unknown) {
    // eslint-disable-next-line no-console
    console.error('UI ErrorBoundary caught:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex items-center justify-center min-h-[60vh] p-6">
          <div className="max-w-md w-full bg-white border border-red-200 rounded-xl shadow-sm p-6 text-center">
            <div className="w-10 h-10 rounded-full bg-red-100 text-red-600 flex items-center justify-center mx-auto mb-3 text-xl font-bold">
              !
            </div>
            <h2 className="text-base font-bold text-gray-900 mb-1">Something went wrong on this page</h2>
            <p className="text-sm text-gray-600 mb-4">
              The view failed to render. Your data is safe — dismiss to retry, or reload.
            </p>
            <pre className="text-[11px] text-left text-gray-500 bg-gray-50 border border-gray-100 rounded p-2 mb-4 overflow-auto max-h-32">
              {this.state.error.message || String(this.state.error)}
            </pre>
            <div className="flex gap-2 justify-center">
              <button
                onClick={() => this.setState({ error: null })}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                Dismiss
              </button>
              <button
                onClick={() => window.location.reload()}
                className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg"
              >
                Reload page
              </button>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

/** Route-aware error boundary: catches render errors and auto-clears when the
 *  user navigates to a different path. Must be rendered inside the Router. */
export default function ErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation()
  return <Boundary resetKey={location.pathname}>{children}</Boundary>
}

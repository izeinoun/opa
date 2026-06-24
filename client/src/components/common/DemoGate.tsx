// Legacy demo gate component (deprecated).
// JWT authentication is now handled by ProtectedRoute in App.tsx and LoginPage.
// This component is kept as a pass-through for backward compatibility.
import { ReactNode } from 'react'

export default function DemoGate({ children }: { children: ReactNode }) {
  return <>{children}</>
}

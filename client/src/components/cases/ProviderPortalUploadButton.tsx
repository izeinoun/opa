import { useState } from 'react'
import { Upload, CheckCircle, AlertCircle, Loader } from 'lucide-react'
import type { CaseDetail } from '../../types'

interface ProviderPortalUploadButtonProps {
  case_: CaseDetail
  onSuccess?: () => void
  onError?: (error: string) => void
}

export default function ProviderPortalUploadButton({
  case_,
  onSuccess,
  onError,
}: ProviderPortalUploadButtonProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')

  // Show button for relevant case statuses
  const canUpload = ['ready_for_notice', 'notice_sent', 'provider_responded', 'reconciling'].includes(case_.status)

  const handleUpload = async () => {
    if (!canUpload) return

    setIsLoading(true)
    setStatus('idle')
    setMessage('')

    try {
      const response = await fetch(
        `/api/provider-portal/upload-recoup-notice?case_id=${case_.case_id}&portal_key=default&headless=true`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      )

      const result = await response.json()

      if (result.success) {
        setStatus('success')
        setMessage('✓ Notice uploaded to provider portal')
        onSuccess?.()
      } else {
        setStatus('error')
        setMessage(`Upload failed: ${result.message}`)
        onError?.(result.message)
      }
    } catch (error) {
      setStatus('error')
      const errorMsg = error instanceof Error ? error.message : 'Unknown error'
      setMessage(`Error: ${errorMsg}`)
      onError?.(errorMsg)
    } finally {
      setIsLoading(false)
    }
  }

  if (!canUpload) {
    return null
  }

  return (
    <div className="space-y-2">
      <button
        onClick={handleUpload}
        disabled={isLoading}
        className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-all ${
          isLoading
            ? 'bg-gray-100 text-gray-500 cursor-not-allowed'
            : 'bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800'
        }`}
      >
        {isLoading ? (
          <>
            <Loader className="w-4 h-4 animate-spin" />
            Uploading...
          </>
        ) : (
          <>
            <Upload className="w-4 h-4" />
            Upload to Provider Portal
          </>
        )}
      </button>

      {/* Status messages */}
      {status === 'success' && (
        <div className="flex items-start gap-2 p-3 bg-green-50 border border-green-200 rounded-lg">
          <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-green-900">{message}</p>
            <p className="text-xs text-green-800 mt-1">
              The recoup notice has been sent to the provider's portal.
            </p>
          </div>
        </div>
      )}

      {status === 'error' && (
        <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-red-900">{message}</p>
            <p className="text-xs text-red-800 mt-1">
              Please try again or contact support if the problem persists.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

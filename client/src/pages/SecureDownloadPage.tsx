import { useSearchParams } from 'react-router-dom'
import { useState } from 'react'
import { AlertCircle, CheckCircle, Download } from 'lucide-react'
import api from '../services/api'

export default function SecureDownloadPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const [npi, setNpi] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [npiVerified, setNpiVerified] = useState(false)
  const [attempts, setAttempts] = useState(0)
  const [locked, setLocked] = useState(false)

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100 px-4">
        <div className="w-full max-w-md bg-white rounded-lg shadow-lg p-8">
          <div className="flex justify-center mb-4">
            <AlertCircle className="w-12 h-12 text-red-600" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 text-center mb-2">Access Expired</h1>
          <p className="text-gray-600 text-center">
            This link has expired or is invalid. Please request a new download link from your payer.
          </p>
        </div>
      </div>
    )
  }

  const handleVerifyNPI = async (e: React.FormEvent) => {
    e.preventDefault()
    if (locked) {
      setError('Too many failed attempts. Please request a new link from your payer.')
      return
    }

    setLoading(true)
    setError(null)

    try {
      await api.post('/secure-download/verify', { token, npi })
      setNpiVerified(true)
    } catch (err: any) {
      const newAttempts = attempts + 1
      setAttempts(newAttempts)
      if (newAttempts >= 3) {
        setLocked(true)
        setError('Too many failed attempts. Please request a new link from your payer.')
      } else {
        setError('The information you entered does not match. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = async () => {
    try {
      const response = await api.get(`/secure-download/file?token=${encodeURIComponent(token)}`, {
        responseType: 'blob',
      })
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', 'claim-recovery-letter.pdf')
      document.body.appendChild(link)
      link.click()
      link.parentElement?.removeChild(link)
    } catch (err: any) {
      setError('Failed to download file. Please try again or contact your payer.')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 px-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow-lg p-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Download Claim Recovery Letter</h1>
        <p className="text-gray-600 mb-6">
          Please enter your billing NPI to access your letter.
        </p>

        {npiVerified ? (
          <div className="space-y-4">
            <div className="flex items-center gap-3 p-4 bg-green-50 border border-green-200 rounded-lg">
              <CheckCircle className="w-6 h-6 text-green-600 flex-shrink-0" />
              <span className="text-green-800 font-semibold">NPI verified successfully</span>
            </div>

            <button
              onClick={handleDownload}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition-colors"
            >
              <Download className="w-5 h-5" />
              Download Letter
            </button>

            <p className="text-sm text-gray-500 text-center">
              The letter will be downloaded as a PDF file to your computer.
            </p>
          </div>
        ) : (
          <form onSubmit={handleVerifyNPI} className="space-y-4">
            <div>
              <label htmlFor="npi" className="block text-sm font-semibold text-gray-700 mb-2">
                Billing NPI
              </label>
              <input
                id="npi"
                type="text"
                inputMode="numeric"
                value={npi}
                onChange={(e) => setNpi(e.target.value.replace(/\D/g, '').slice(0, 10))}
                placeholder="10-digit NPI"
                maxLength={10}
                disabled={locked}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500"
              />
            </div>

            {error && (
              <div className="flex gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
                <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                <div>{error}</div>
              </div>
            )}

            {!locked && attempts > 0 && attempts < 3 && (
              <p className="text-sm text-amber-700 text-center">
                {3 - attempts} attempt{3 - attempts === 1 ? '' : 's'} remaining
              </p>
            )}

            <button
              type="submit"
              disabled={loading || locked || npi.length !== 10}
              className="w-full px-4 py-2 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Verifying...' : 'Continue'}
            </button>
          </form>
        )}

        <div className="mt-6 p-4 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-600">
          <p className="font-semibold text-gray-700 mb-1">Link Expiration</p>
          <p>This link will expire in 24 hours. If you have questions, contact your payer.</p>
        </div>
      </div>
    </div>
  )
}

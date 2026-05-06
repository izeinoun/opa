import { Printer } from 'lucide-react'
import type { RenderedLetter } from '../../types'
import { formatDate } from '../../utils/dateUtils'

interface Props {
  letter: RenderedLetter | null
  isLoading?: boolean
}

export default function LetterViewer({ letter, isLoading = false }: Props) {
  if (isLoading) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg p-8 animate-pulse">
        <div className="h-6 bg-gray-100 rounded w-1/3 mb-4" />
        <div className="space-y-2">
          {[...Array(8)].map((_, i) => (
            <div key={i} className={`h-4 bg-gray-100 rounded ${i % 3 === 2 ? 'w-2/3' : 'w-full'}`} />
          ))}
        </div>
      </div>
    )
  }

  if (!letter) {
    return (
      <div className="bg-white border border-dashed border-gray-300 rounded-lg p-12 text-center">
        <p className="text-gray-400 text-sm">Select a case and template, then click Preview.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-500">
          Template: <span className="font-mono font-semibold text-gray-700">{letter.template_code}</span>
          {' '}&bull;{' '}
          Rendered: {formatDate(letter.rendered_at)}
        </div>
        <button
          onClick={() => window.print()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 text-white text-sm rounded hover:bg-gray-700 transition-colors"
        >
          <Printer className="w-4 h-4" />
          Print
        </button>
      </div>

      <div
        className="bg-white border border-gray-200 rounded-lg p-10 shadow-sm print:shadow-none print:border-none print:p-0"
        style={{ fontFamily: 'Georgia, serif', lineHeight: '1.7' }}
        dangerouslySetInnerHTML={{ __html: letter.html_content }}
      />
    </div>
  )
}

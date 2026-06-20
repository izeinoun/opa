// Dedicated home for system-generated result documents (recoupment letters),
// kept separate from the File Intake page so inputs vs. outputs don't blur.
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Eye, Download } from 'lucide-react'
import { listOutputFiles } from '../services/recoupmentService'
import { viewOutputFile } from '../services/fileView'
import { API_BASE } from '../services/api'

export default function OutputFilesPage() {
  const { data: outputs = [] } = useQuery({
    queryKey: ['intake-outputs'],
    queryFn: () => listOutputFiles(),
  })

  return (
    <div className="flex flex-col gap-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Output Files</h1>
        <p className="text-sm text-gray-500 mt-1">
          System-generated result documents — provider recoupment letters produced
          from reviewed cases. Generate one from a case&apos;s <strong>Output</strong> tab.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {outputs.length === 0 ? (
          <p className="px-5 py-12 text-center text-sm text-gray-400">
            No output files yet.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
                <th className="px-5 py-2.5">File</th>
                <th className="px-3 py-2.5">Type</th>
                <th className="px-3 py-2.5">Case</th>
                <th className="px-3 py-2.5">Generated</th>
                <th className="px-3 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {outputs.map((o) => (
                <tr key={o.document_id} className="border-t border-gray-50 hover:bg-gray-50">
                  <td className="px-5 py-2.5 font-mono text-xs text-gray-700 max-w-[280px] truncate" title={o.filename}>
                    {o.filename}
                  </td>
                  <td className="px-3 py-2.5 text-gray-600">Recoupment letter</td>
                  <td className="px-3 py-2.5">
                    {o.case_sequence != null ? (
                      <Link to={`/cases/${o.case_sequence}`} className="text-[#FE017D] hover:underline font-medium">
                        {o.case_number ?? 'View case'}
                      </Link>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-gray-600">{o.uploaded_at.slice(0, 10)}</td>
                  <td className="px-3 py-2.5 text-right whitespace-nowrap">
                    <button
                      onClick={() => viewOutputFile(o.document_id).catch(() => alert('Could not open this file.'))}
                      className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-700 transition-colors"
                      title="View file"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                    <a
                      href={`${API_BASE}/file-intake/outputs/${o.document_id}/download`}
                      className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-700 transition-colors ml-1 inline-block align-middle"
                      title="Download file"
                    >
                      <Download className="w-4 h-4" />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

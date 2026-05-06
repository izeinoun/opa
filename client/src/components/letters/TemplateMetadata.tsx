import type { LetterTemplate } from '../../types'
import { formatDate } from '../../utils/dateUtils'

interface Props {
  template: LetterTemplate
}

const LOB_COLORS: Record<string, string> = {
  MA: 'bg-blue-100 text-blue-800',
  PPO: 'bg-green-100 text-green-800',
  Medicaid: 'bg-purple-100 text-purple-800',
}

const TYPE_COLORS: Record<string, string> = {
  initial_demand: 'bg-orange-100 text-orange-800',
  second_notice: 'bg-red-100 text-red-800',
  final_notice: 'bg-rose-100 text-rose-800',
  acknowledgment: 'bg-cyan-100 text-cyan-800',
  resolution: 'bg-green-100 text-green-800',
}

export default function TemplateMetadata({ template }: Props) {
  const lobColor = LOB_COLORS[template.lob] ?? 'bg-gray-100 text-gray-800'
  const typeColor = TYPE_COLORS[template.template_type] ?? 'bg-gray-100 text-gray-800'

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 hover:border-opa-500 transition-colors">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <span className="text-xs font-mono text-gray-500">{template.code}</span>
          <h4 className="text-sm font-semibold text-gray-800 mt-0.5">{template.name}</h4>
        </div>
        <span
          className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
            template.is_active
              ? 'bg-green-100 text-green-700'
              : 'bg-gray-100 text-gray-500'
          }`}
        >
          {template.is_active ? 'Active' : 'Inactive'}
        </span>
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${lobColor}`}>
          {template.lob}
        </span>
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${typeColor}`}>
          {template.template_type.replace(/_/g, ' ')}
        </span>
        <span className="px-1.5 py-0.5 rounded text-xs bg-gray-50 text-gray-600 border border-gray-200">
          v{template.version}
        </span>
      </div>

      <p className="mt-2 text-xs text-gray-400">Created {formatDate(template.created_at)}</p>
    </div>
  )
}

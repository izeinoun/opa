import { Shield, Database, Settings, BookOpen, FileText, ChevronRight } from 'lucide-react'

export type AdminSection =
  | 'freshness' | 'users'
  | 'rules' | 'prioritization' | 'model'
  | 'cpt' | 'icd' | 'drg' | 'modifiers'
  | 'letter-templates' | 'doc-templates'

interface NavItem { id: AdminSection; label: string }
interface NavGroup { label: string; icon: React.ReactNode; items: NavItem[] }

const GROUPS: NavGroup[] = [
  {
    label: 'System',
    icon: <Settings className="w-3.5 h-3.5" />,
    items: [
      { id: 'freshness', label: 'Reference Data' },
      { id: 'users',     label: 'Users' },
    ],
  },
  {
    label: 'Detection',
    icon: <Shield className="w-3.5 h-3.5" />,
    items: [
      { id: 'rules',          label: 'Detector Rules' },
      { id: 'prioritization', label: 'Prioritization' },
      { id: 'model',          label: 'ML Model' },
    ],
  },
  {
    label: 'Reference Data',
    icon: <Database className="w-3.5 h-3.5" />,
    items: [
      { id: 'cpt',       label: 'CPT / HCPCS Codes' },
      { id: 'icd',       label: 'ICD-10 Codes' },
      { id: 'drg',       label: 'DRG Codes' },
      { id: 'modifiers', label: 'Modifiers' },
    ],
  },
  {
    label: 'Templates',
    icon: <FileText className="w-3.5 h-3.5" />,
    items: [
      { id: 'letter-templates', label: 'Letter Templates' },
      { id: 'doc-templates',    label: 'Document Templates' },
    ],
  },
]

interface Props {
  active: AdminSection
  onChange: (s: AdminSection) => void
}

export default function AdminSidebar({ active, onChange }: Props) {
  return (
    <nav className="w-52 flex-shrink-0 border-r border-gray-200 bg-white flex flex-col">
      <div className="px-4 pt-4 pb-3 border-b border-gray-100 flex items-center gap-2">
        <BookOpen className="w-4 h-4 text-[#1e3a5f]" />
        <span className="text-sm font-semibold text-gray-900">Admin</span>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {GROUPS.map(group => (
          <div key={group.label} className="mb-1">
            <div className="flex items-center gap-1.5 px-4 py-1.5 mt-1">
              <span className="text-gray-400">{group.icon}</span>
              <span className="text-[11px] font-semibold uppercase tracking-widest text-gray-400">
                {group.label}
              </span>
            </div>
            {group.items.map(item => (
              <button
                key={item.id}
                onClick={() => onChange(item.id)}
                className={`w-full text-left flex items-center justify-between px-4 py-1.5 text-sm transition-colors
                  ${active === item.id
                    ? 'bg-[#FE017D]/8 text-[#FE017D] font-medium border-r-2 border-[#FE017D]'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
              >
                {item.label}
                {active === item.id && <ChevronRight className="w-3 h-3 opacity-60" />}
              </button>
            ))}
          </div>
        ))}
      </div>
    </nav>
  )
}

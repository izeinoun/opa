// Persistent assistant drawer that lives on the right side of PayGuard.
// Integrated into layout (not overlay) - squishes center content when expanded.
// Supports two width modes: normal (480px) and wide (624px) for rich content.
import { ChevronRight, Bot, Maximize2, Minimize2 } from 'lucide-react'
import AssistantPanel from './AssistantPanel'
import type { ChatContext } from '../../types/assistant'

interface Props {
  isCollapsed: boolean
  onToggle: () => void
  context?: ChatContext
  isWideMode?: boolean
  onToggleWideMode?: () => void
}

export default function AssistantDrawer({ isCollapsed, onToggle, context, isWideMode = false, onToggleWideMode }: Props) {
  if (isCollapsed) {
    // Collapsed: just icon bar
    return (
      <div className="w-full h-full flex flex-col items-center py-3 gap-2 bg-white border-l border-gray-200">
        <button
          onClick={onToggle}
          title="Expand assistant"
          className="text-gray-400 hover:text-gray-700 transition-colors p-1"
          aria-label="Expand assistant"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
        <div className="w-6 h-6 rounded-lg bg-[#FE017D]/10 flex items-center justify-center flex-shrink-0">
          <Bot className="w-3 h-3 text-[#FE017D]" />
        </div>
      </div>
    )
  }

  // Expanded: full drawer with assistant panel
  return (
    <div className="w-full h-full flex flex-col bg-white border-l border-gray-200 overflow-hidden">
      {/* Header with width toggle and collapse buttons */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-100 bg-gray-50/60 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-6 h-6 rounded-lg bg-[#FE017D]/10 flex items-center justify-center flex-shrink-0">
            <Bot className="w-3 h-3 text-[#FE017D]" />
          </div>
          <p className="text-xs font-semibold text-gray-800 truncate">Assistant</p>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={onToggleWideMode}
            title={isWideMode ? 'Normal width' : 'Wide view'}
            className={`transition-colors p-1 rounded-md ${
              isWideMode
                ? 'text-[#FE017D] hover:bg-[#FE017D]/10'
                : 'text-gray-400 hover:text-gray-700 hover:bg-gray-200'
            }`}
            aria-label={isWideMode ? 'Normal width' : 'Wide view'}
          >
            {isWideMode ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
          <button
            onClick={onToggle}
            title="Collapse assistant"
            className="text-gray-400 hover:text-gray-700 transition-colors p-1 rounded-md hover:bg-gray-200"
            aria-label="Collapse assistant"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Assistant panel content */}
      <div className="flex-1 overflow-hidden">
        <AssistantPanel
          open={true}
          onClose={() => {}}
          isDrawerMode={true}
          context={context}
        />
      </div>
    </div>
  )
}

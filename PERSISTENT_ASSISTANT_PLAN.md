# Persistent Assistant Drawer Implementation Plan

## Overview

Transform the PayGuard assistant from a modal slide-over panel to a persistent right-side drawer that stays active and follows the user through the application, creating a "live assistant" experience.

---

## Vision

**Current:** Assistant is modal, user opens/closes on demand
**Future:** Assistant lives on the right side, always available, follows navigation context

```
BEFORE:
┌─────────────────────────────────────┐
│            TopBar                   │
├──────────┬──────────────────────────┤
│ SideNav  │   Main Content (Full W)  │
│          │   [Click Assistant →     │
│          │    Modal opens]          │
└──────────┴──────────────────────────┘

AFTER:
┌─────────────────────────────────────┐
│            TopBar                   │
├──────────┬──────────────┬───────────┤
│ SideNav  │Main Content  │Assistant  │
│          │(70%)         │(30%)      │
│          │              │[Collapse ◀]
└──────────┴──────────────┴───────────┘
```

---

## Implementation Phases

### Phase 1: Basic Persistent Drawer (This Sprint)

**Goals:**
- ✅ Restructure layout to side-by-side
- ✅ Make assistant always visible on right
- ✅ Add collapse/expand toggle
- ✅ Persist collapsed state to localStorage
- ✅ Auto-update assistant context on navigation
- ✅ Desktop-first (responsive refinement in Phase 3)

**Effort:** ~1 day (8 hours)

**Components to Change:**
1. `App.tsx` — Layout restructuring
2. `TopBar.tsx` — Maybe adjust spacing
3. `AssistantPanel.tsx` — Change from modal to persistent drawer
4. State management — Context provider for assistant state

---

### Phase 2: Polish & Refinements (Future)

**Goals:**
- [ ] Resizable divider between main content and assistant
- [ ] Keyboard shortcuts (Cmd+L to toggle)
- [ ] Smooth collapse/expand animations
- [ ] Width preference memory (localStorage)
- [ ] Better visual hierarchy
- [ ] Context switching behavior refinement

**Effort:** ~4 hours

---

### Phase 3: Responsive Design & Mobile (Future)

**Goals:**
- [ ] Hide assistant on mobile, show as bottom sheet
- [ ] Tablet: Collapsible by default with icon
- [ ] Mobile: Separate "Assistant" tab or slide-up modal
- [ ] Responsive breakpoints tested

**Effort:** ~4 hours

---

## Phase 1 Detailed Tasks

### Task 1: Layout Restructuring (`App.tsx`)

**Current Structure:**
```tsx
<BrowserRouter>
  <div className="flex flex-col h-screen">
    <TopBar />
    <div className="flex flex-1">
      <SideNav />
      <main className="flex-1">
        <Routes>...</Routes>
      </main>
    </div>
  </div>
</BrowserRouter>
```

**Target Structure:**
```tsx
<BrowserRouter>
  <div className="flex flex-col h-screen">
    <TopBar />
    <div className="flex flex-1 gap-0">
      <SideNav />
      <main className={`flex-1 overflow-auto transition-all ${
        assistantCollapsed ? 'w-full' : 'w-[calc(100%-350px)]'
      }`}>
        <Routes>...</Routes>
      </main>
      {/* Assistant drawer always visible */}
      <AssistantDrawer 
        isCollapsed={assistantCollapsed}
        onToggle={toggleAssistant}
        context={currentContext}
      />
    </div>
  </div>
</BrowserRouter>
```

**Changes:**
- Wrap main content and assistant in flex container
- Add collapse state to App
- Pass context to assistant
- Update main content width based on collapse state

---

### Task 2: Create AssistantDrawer Component

**New File:** `/client/src/components/assistant/AssistantDrawer.tsx`

**Props:**
```tsx
interface Props {
  isCollapsed: boolean
  onToggle: () => void
  context?: ChatContext
  busy?: boolean
}
```

**Features:**
- Display AssistantPanel when not collapsed
- Show collapsed icon/bar when collapsed
- Width: 350px (not collapsed), 40px (collapsed)
- Smooth transitions
- Always visible, no close button

---

### Task 3: Update AssistantPanel for Drawer Mode

**File:** `/client/src/components/assistant/AssistantPanel.tsx`

**Changes:**
- Remove close button (only collapse button)
- Adjust max-height if needed
- Ensure it fills the drawer container
- No modal overlay
- Fixed positioning within drawer

---

### Task 4: Add Context Provider for Shared State

**New File:** `/client/src/hooks/useAssistantState.ts`

```tsx
interface AssistantState {
  isCollapsed: boolean
  toggleCollapsed: () => void
  context: ChatContext | null
  updateContext: (ctx: ChatContext) => void
}

export const useAssistantState = (): AssistantState => {
  // Manage collapsed state, context, etc.
}
```

---

### Task 5: Auto-Update Context on Route Change

**Update:** Routes/page components

Add effect to update assistant context when navigation changes:
```tsx
useEffect(() => {
  // When case opens, update assistant
  assistant.updateContext({ 
    active_case_id: caseId,
    active_view: 'case'
  })
}, [caseId])
```

---

### Task 6: Persist Collapsed State

**Implementation:**
```tsx
// On toggle
const toggleAssistant = () => {
  const newState = !assistantCollapsed
  setAssistantCollapsed(newState)
  localStorage.setItem('assistant_collapsed', String(newState))
}

// On mount
useEffect(() => {
  const saved = localStorage.getItem('assistant_collapsed')
  if (saved !== null) {
    setAssistantCollapsed(saved === 'true')
  }
}, [])
```

---

## File Changes Summary

### New Files
- [ ] `/client/src/components/assistant/AssistantDrawer.tsx`
- [ ] `/client/src/hooks/useAssistantState.ts`
- [ ] `/client/src/lib/assistantContext.ts` (if needed)

### Modified Files
- [ ] `/client/src/App.tsx` — Layout restructuring
- [ ] `/client/src/components/assistant/AssistantPanel.tsx` — Remove modal behavior
- [ ] `/client/src/pages/*.tsx` — Add context updates on mount

---

## CSS/Styling Notes

**Tailwind Classes to Use:**
```tsx
// Main content when assistant is visible
"flex-1 transition-all duration-300"

// Assistant drawer
"w-[350px] border-l border-gray-200 bg-white overflow-hidden flex flex-col"

// Collapsed assistant bar
"w-10 border-l border-gray-200 bg-white overflow-hidden flex flex-col items-center py-2"

// Collapse button
"text-gray-400 hover:text-gray-700 transition-colors p-1"
```

---

## State Management

### App-level state:
```tsx
const [assistantCollapsed, setAssistantCollapsed] = useState(() => {
  const saved = localStorage.getItem('assistant_collapsed')
  return saved ? JSON.parse(saved) : false
})

const [assistantContext, setAssistantContext] = useState<ChatContext | null>(null)
```

### Pass through props:
```tsx
<AssistantDrawer
  isCollapsed={assistantCollapsed}
  onToggle={() => setAssistantCollapsed(!assistantCollapsed)}
  context={assistantContext}
/>
```

---

## Testing Checklist (Phase 1)

- [ ] Layout renders correctly (main content + drawer side-by-side)
- [ ] Collapse button works
- [ ] Collapsed state persists on page refresh
- [ ] Assistant receives context updates on navigation
- [ ] No layout shift when toggling
- [ ] Smooth transitions
- [ ] No console errors
- [ ] Desktop viewport tested (1920x1080, 1440x900, 1366x768)
- [ ] Scroll behavior works in both panels
- [ ] TopBar still visible and functional

---

## Known Limitations (Phase 1)

- ⚠️ Mobile not optimized (will hide assistant on small screens in Phase 3)
- ⚠️ Drawer width is fixed (resizable in Phase 2)
- ⚠️ No keyboard shortcuts (Phase 2)
- ⚠️ No animations yet (Phase 2)
- ⚠️ Limited context handling (basic passthrough only)

---

## Future Enhancements (Post-Phase 1)

### Phase 2
- [ ] Resizable divider with min/max widths
- [ ] Keyboard shortcut (Cmd+L)
- [ ] Width preference in localStorage
- [ ] Smooth collapse/expand animation
- [ ] "Follow mode" toggle
- [ ] Better visual divider styling

### Phase 3
- [ ] Mobile responsive design
- [ ] Tablet optimization
- [ ] Touch-friendly collapse button
- [ ] Alternative UI for small screens

### Future Phases
- [ ] AI proactive suggestions based on context
- [ ] Quick action buttons from assistant
- [ ] Conversation history clear button
- [ ] Assistant settings/preferences
- [ ] Context-aware tool suggestions

---

## Rollback Plan

If issues arise, can revert to modal-only by:
1. Restore original `App.tsx` layout
2. Remove AssistantDrawer component
3. Bring back AssistantPanel as slide-over modal
4. Takes ~15 minutes to rollback

---

## Success Criteria

✅ Assistant is always visible on right side
✅ User can collapse/expand it
✅ Collapsed state persists
✅ Assistant context updates with navigation
✅ No layout breaks or shifted content
✅ Smooth UX without jank
✅ Desktop viewport works well (1920px down to 1366px)

---

## Timeline

- **Phase 1:** This sprint (1 day)
- **Phase 2:** Next sprint (4 hours, lower priority)
- **Phase 3:** Future (when mobile support needed)

---

## Notes for Future Implementation

- Keyboard shortcuts should use `useEffect` with `window.addEventListener('keydown')`
- Resizable divider can use react-resizable or custom drag handler
- Mobile detection: `window.innerWidth < 768` for breakpoint
- Keep assistant scroll state when collapsing
- Consider if context should auto-clear on logout

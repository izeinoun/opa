# Phase 2: Notes & Follow-up Items

**Status:** Planning  
**Target:** Next iteration

---

## Build Cleanup

### TypeScript Errors in AssistantPanel.tsx

**Status:** ⚠️ Known issue (non-blocking)

When running `npm run build`, you'll see ~5 TypeScript errors in AssistantPanel.tsx around the modal rendering code (lines 500+). These are in the modal fallback path which isn't used in the new persistent drawer layout.

**Impact:** 
- ✅ Dev server works fine (Vite transpiles JS even with TS errors)
- ✅ New drawer mode works perfectly
- ❌ `npm run build` will fail (needs tsc to pass)

**Fix (Phase 2):**
Option A: Extract modal rendering to separate file
```
AssistantPanel.tsx → AssistantPanelDrawer.tsx + AssistantPanelModal.tsx
```

Option B: Remove modal code entirely (if no longer needed)
```
Delete lines 430-650 (old modal rendering)
Keep only drawer path
```

Option C: Fix the modal code
```
Add missing imports/variables
Complete the modal rendering section
```

**Recommendation:** Option B (simplest) — modal assistant isn't used anymore since we have persistent drawer. Check if any other code depends on modal behavior first.

---

## Suggested Phase 2 Work (Priority Order)

### High Priority
1. **Fix build errors** (30 min)
   - Choose one of the above options
   - Get `npm run build` passing with 0 errors
   - Prerequisite for production deployment

### Medium Priority
2. **Resizable divider** (6 hours)
   - Drag between main content and assistant
   - Min/max width guards (min nav 40px, max assistant 700px)
   - Persist custom widths per mode
   - Smooth dragging with cursor feedback

3. **Keyboard shortcuts** (3 hours)
   - Cmd/Ctrl+Shift+A: Toggle assistant collapse
   - Cmd/Ctrl+Shift+N: Toggle nav collapse
   - Cmd/Ctrl+Shift+W: Toggle width mode
   - Show hint in drawer header

### Lower Priority
4. **Mobile responsive** (8 hours)
   - <768px: Hide drawer, show bottom sheet tab
   - <1024px: Default narrow, option to widen
   - Touch-friendly buttons

5. **Smart width detection** (4 hours)
   - Auto-wide when assistant has rich content
   - Auto-normal when chat is empty
   - Learn user preference per view (case vs. dashboard)

---

## Testing Baseline

Before Phase 2 work, establish baseline:

```bash
# Clean build
npm run clean
npm install
npm run build  # Should have 0 errors

# Dev mode
npm run dev
# Open http://localhost:5174
# Test all features work
```

---

## Code Review Checklist (Before Merge)

- [ ] All TypeScript errors fixed
- [ ] `npm run build` passes with 0 warnings/errors
- [ ] No console errors in dev mode
- [ ] Test all collapse/expand combos
- [ ] Test width mode toggle
- [ ] Verify localStorage persistence
- [ ] Test on 1920px, 1440px, 1366px widths
- [ ] Responsive fine on 1024px (tablet)
- [ ] No layout shift during transitions

---

## Future Enhancements (Phase 3+)

- Auto-suggest wide mode based on assistant response length
- Context-aware width (wide by default for case detail)
- Drawer peek mode (collapsed with content preview)
- Animation preferences (respect prefers-reduced-motion)
- Drag-to-scroll main content while assistant open
- Custom theme colors for drawer header
- Assistant keyboard focus trap (when open)

---

## Deployment Checklist

Before production:
- [ ] Phase 1 build errors fixed
- [ ] All tests passing
- [ ] No console errors in production build
- [ ] Mobile breakpoint acceptable (or deferred to Phase 3)
- [ ] localStorage namespacing reviewed (no collisions?)
- [ ] CLAUDE.md updated with new features
- [ ] README updated with architecture changes
- [ ] Rollback plan documented (easy revert to modal if needed)

---

## Notes

- **localStorage keys** to be aware of:
  - `payguard_nav_collapsed`
  - `payguard_assistant_collapsed`
  - `payguard_assistant_wide_mode`

- **Transition timing** (300ms) is well-tuned for current layout — don't change without UX testing

- **Width calculations** are responsive — if you add new components, verify flex layout still works

- **Assistant context** updates are automatic via route detection — no manual wiring needed for new pages

---

Generated: 2026-06-24

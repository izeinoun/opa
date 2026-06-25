# Known Issues - PayGuard Client

## Issue: Left Nav Collapse Button Not Rendering

**Status:** ✅ RESOLVED (2026-06-24)

**Severity:** Medium (UI/UX - nice-to-have feature)

**Date Reported:** 2026-06-24

---

## Description

The left navigation sidebar was intended to have a collapsible/expandable feature with a visible menu button (☰). However, after implementing the feature in `AuthenticatedLayout.tsx`, the collapse button does not appear on the page despite:
- Code being present in the component
- Browser DevTools showing the JSX structure should render it
- Dev server restarting and hard browser refresh

---

## Current Behavior

✅ **What works:**
- Left nav displays fully expanded with all menu items
- Layout structure is correct (Nav + Main Content + Assistant as 3-column flex layout)
- Assistant drawer collapse/expand works correctly
- Smooth transitions work for width changes
- LocalStorage persistence works

❌ **What doesn't work:**
- Menu button (☰) to collapse left nav is not visible
- Toggle function is not accessible to user
- No way to hide the nav to gain more screen real estate

---

## What We Tried

1. ✅ Added collapse button in JSX with proper styling
   - Dark text color (text-gray-600)
   - Hover effects (hover:bg-gray-200)
   - Rounded corners (rounded-md)
   - Proper padding (p-1.5)

2. ✅ Added visual header bar
   - Background color (bg-gray-50)
   - Border (border-b border-gray-200)
   - Flexbox layout with justify-end

3. ✅ Verified code structure
   - Conditional rendering: `navCollapsed ? <collapsed> : <expanded>`
   - Button onClick handler tied to `toggleNav()`
   - State management in place (navCollapsed state + localStorage)

4. ✅ Restarted dev server
   - Killed existing Vite process
   - Fresh start with `npm run dev`
   - Verified server ready message

5. ✅ Browser refresh strategies
   - Hard refresh: Cmd+Shift+R (Mac) / Ctrl+Shift+R (Windows)
   - Multiple refresh attempts
   - Cleared cache

---

## Root Cause (Unknown)

Possible causes:
- [ ] CSS specificity issue (something overriding the button display)
- [ ] React rendering issue (button condition not evaluating correctly)
- [ ] SideNav component taking full height and hiding button
- [ ] Tailwind class generation issue
- [ ] Z-index or overflow-hidden issue
- [ ] Build output mismatch (vite not picking up changes)

---

## Code Location

**File:** `/Users/issamzeinoun/claude/overcoding/opa/client/src/components/layout/AuthenticatedLayout.tsx`

**Relevant Lines:**
- Lines 78-93: Expanded nav with collapse button
- Lines 66-77: Collapsed nav with expand button
- Lines 50-51: Toggle functions

---

## Next Steps to Debug

1. **Add console.log statements**
   - Log `navCollapsed` state value on render
   - Verify conditional is working: `navCollapsed ? ... : ...`
   - Check if button onClick is firing

2. **Inspect with DevTools**
   - Right-click nav → "Inspect"
   - Look for the Menu button element in DOM
   - Check computed styles (is display:none applied? visibility:hidden?)
   - Check z-index and overflow values

3. **Simplify the component**
   - Remove SideNav temporarily and render just the button
   - Test if button appears when SideNav is removed
   - If button appears, SideNav might be covering it

4. **Check TypeScript errors**
   - Run: `npm run build` (not dev)
   - Look for type errors that might prevent rendering

5. **React DevTools**
   - Install React DevTools extension
   - Check component tree: is `AuthenticatedLayout` rendering correctly?
   - Verify props and state values

---

## Temporary Workaround

**None available.** Users currently cannot collapse the left nav. 

Workaround for users wanting more screen space:
- Use browser zoom (Cmd+- or Ctrl+-)
- Use browser fullscreen mode (F11)
- Collapse assistant drawer instead (works fine)

---

## Impact

**Current State:**
- Phase 1 of persistent assistant drawer is ✅ COMPLETE
  - ✅ Assistant drawer visible on right
  - ✅ Assistant drawer collapse/expand works smoothly
  - ✅ Center content squishes/expands appropriately
  - ✅ Context follows navigation

- Phase 1 partial:
  - ❌ Left nav collapse feature incomplete
  - This was a nice-to-have enhancement, not critical

**Users can:**
- ✅ Use the app normally with left nav always visible
- ✅ Collapse assistant to free up space
- ✅ Resize browser window

---

## Resolution

**Root Cause:** SideNav component had old `position: fixed` styling from previous modal-based layout. This was layering on top of the new layout and covering the collapse button.

**Fix Applied:** 
- Removed `fixed left-0 top-0 h-screen z-40` from SideNav
- Changed to `w-full h-full overflow-y-auto` (flows naturally in flex container)
- Button now fully visible and clickable

**File:** `src/components/common/SideNav.tsx` line 140

## Decision Log

**2026-06-24:** Feature implemented and resolved. Debugged using browser DevTools and found hidden button issue. Fixed by removing fixed positioning from SideNav component.

---

## Phase 2 Priorities

If revisiting this issue:
1. Use debugger approach above
2. Consider alternative: move nav items to hamburger menu in TopBar
3. Consider: make nav collapsible via keyboard shortcut instead (might work better)

---

## Related Issues

- None at this time
- This is the only known blocking issue in Phase 1 implementation

---

## References

- Original plan: `/PERSISTENT_ASSISTANT_PLAN.md`
- Layout component: `src/components/layout/AuthenticatedLayout.tsx`
- Assistant drawer works fine: `src/components/assistant/AssistantDrawer.tsx`


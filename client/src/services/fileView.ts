import api from './api'

/**
 * Open a stored file inline in a new browser tab (PDFs/images render in place).
 *
 * The download endpoints require auth headers (X-User-Id + demo token), which a
 * plain <a href> / window.open can't carry — so we fetch the bytes through the
 * authenticated axios instance and hand the browser a blob URL instead.
 *
 * The blank tab is opened SYNCHRONOUSLY on the user's click (before the await)
 * so it survives popup blockers; we then point it at the blob once it loads.
 */
async function openInline(url: string): Promise<void> {
  const tab = window.open('', '_blank')
  try {
    const res = await api.get(url, { params: { inline: true }, responseType: 'blob' })
    const objUrl = URL.createObjectURL(res.data as Blob)
    if (tab) tab.location.href = objUrl
    else window.open(objUrl, '_blank') // sync open was blocked — try once more
    // Give the tab time to load before releasing the object URL.
    window.setTimeout(() => URL.revokeObjectURL(objUrl), 60_000)
  } catch (err) {
    tab?.close()
    throw err
  }
}

/** View a durable document (PayGuard/ClaimGuard case/claim attachment). */
export function viewDocument(documentId: string): Promise<void> {
  return openInline(`/documents/${documentId}/download`)
}

/** View a staged intake file (works for unmatched files with no Document yet). */
export function viewIntakeFile(intakeId: string): Promise<void> {
  return openInline(`/file-intake/${intakeId}/download`)
}

/** View a generated output document (recoupment letter) from the Intake Portal,
 *  via the file-intake-scoped route so the portal's admin/intake auth suffices. */
export function viewOutputFile(documentId: string): Promise<void> {
  return openInline(`/file-intake/outputs/${documentId}/download`)
}

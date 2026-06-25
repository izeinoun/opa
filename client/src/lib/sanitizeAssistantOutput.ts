/**
 * Sanitize assistant output by removing markup that shouldn't be visible to users:
 * - Code blocks (``` ... ```)
 * - Follow-up suggestions (@@FOLLOWUPS@@ [...])
 */
export function sanitizeAssistantOutput(text: string): string {
  // Remove markdown code blocks (``` ... ```)
  let cleaned = text.replace(/```[\s\S]*?```/g, '')

  // Remove @@FOLLOWUPS@@ markup and its JSON array
  cleaned = cleaned.replace(/@@FOLLOWUPS@@\s*\[[\s\S]*?\]/g, '')

  // Clean up excessive whitespace (multiple blank lines → single blank line)
  cleaned = cleaned.replace(/\n\n\n+/g, '\n\n')

  // Trim leading/trailing whitespace
  cleaned = cleaned.trim()

  return cleaned
}

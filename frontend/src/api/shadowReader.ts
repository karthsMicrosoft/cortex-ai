/**
 * Shadow Reader API client — US-8.
 *
 * Typed wrappers around:
 *   GET  /api/notes/{id}/shadow-reader
 *   POST /api/notes/{id}/shadow-reader/answer
 *   POST /api/notes/{id}/shadow-reader/dismiss
 *   PUT  /api/users/me/shadow-reader/settings
 */
import { apiGet, apiPost, apiPut } from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ShadowReaderStatus =
  | 'pending'
  | 'asked'
  | 'answered'
  | 'dismissed'
  | 'skipped';

export interface ShadowReaderQuestionsOut {
  status: ShadowReaderStatus;
  questions: string[];
}

export interface ShadowReaderSettings {
  enabled: boolean;
  disabled_categories: string[];
}

export interface ShadowReaderSettingsOut {
  enabled: boolean;
  disabled_categories: string[];
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Poll for the current shadow reader status and questions for a note.
 * Called on the B17 tiered schedule: 10×2s then 5×5s.
 */
export async function getQuestions(noteId: string): Promise<ShadowReaderQuestionsOut> {
  return apiGet<ShadowReaderQuestionsOut>(`/api/notes/${noteId}/shadow-reader`);
}

/**
 * Submit a text answer to the shadow reader questions.
 * Returns 409 if the note is not in 'asked' state.
 */
export async function answer(noteId: string, text: string): Promise<{ status: string }> {
  return apiPost<{ status: string }>(`/api/notes/${noteId}/shadow-reader/answer`, {
    answer: text,
  });
}

/**
 * Dismiss shadow reader for this note (sets status → 'dismissed').
 * Does not affect future notes.
 */
export async function dismiss(noteId: string): Promise<{ status: string }> {
  return apiPost<{ status: string }>(`/api/notes/${noteId}/shadow-reader/dismiss`);
}

/**
 * Update global shadow reader settings for the authenticated user.
 */
export async function updateSettings(
  payload: ShadowReaderSettings,
): Promise<ShadowReaderSettingsOut> {
  return apiPut<ShadowReaderSettingsOut>(
    '/api/users/me/shadow-reader/settings',
    payload,
  );
}

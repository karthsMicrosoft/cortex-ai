import { apiDelete, apiGet, apiPost, apiPut } from './client';

// ---------------------------------------------------------------------------
// Backend schema types (mirrors NoteOut / NoteCreate from FastAPI)
// ---------------------------------------------------------------------------

export type SourceType = 'voice' | 'text' | 'image';
export type Category = 'Music' | 'Fitness' | 'Journal' | 'Ideas' | 'Spiritual' | 'Learning';
export type ProcessingStatus = 'raw' | 'transcribed' | 'processed' | 'enriched' | 'failed';
export type ShadowReaderStatus = 'pending' | 'asked' | 'answered' | 'dismissed' | 'skipped';

export interface NoteLink {
  id: string;
  source_note_id: string;
  target_note_id: string;
  similarity_score: number;
  link_type: string;
}

export interface NoteOut {
  id: string;
  user_id: string;
  content: string;
  raw_transcription?: string;
  summary?: string;
  source_type: SourceType;
  category: Category;
  audio_url?: string;
  image_url?: string;
  audio_duration_seconds?: number;
  entities: unknown[];
  mood?: string;
  music_metadata: Record<string, unknown>;
  processing_status: ProcessingStatus;
  sync_status: string;
  client_id?: string;
  tags: string[];
  links?: NoteLink[];
  shadow_reader_status?: ShadowReaderStatus;
  shadow_reader_questions?: string[];
  shadow_reader_answer?: string;
  created_at: string;
  updated_at: string;
}

export interface NoteCreate {
  content: string;
  source_type: SourceType;
  category?: Category;
  audio_url?: string;
  image_url?: string;
  client_id?: string;
  tags?: string[];
}

export interface NoteUpdate {
  content?: string;
  category?: Category;
  tags?: string[];
  mood?: string;
  music_metadata?: Record<string, unknown>;
  image_url?: string;
  audio_url?: string;
}

export interface NotesListResponse {
  items: NoteOut[];
  total: number;
}

export interface NotesListFilters {
  category?: Category;
  tag?: string;
  date_from?: string;
  date_to?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// Notes API functions
// ---------------------------------------------------------------------------

function buildQuery(filters: NotesListFilters): string {
  const params = new URLSearchParams();
  if (filters.category) params.set('category', filters.category);
  if (filters.tag) params.set('tag', filters.tag);
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  if (filters.q) params.set('q', filters.q);
  if (filters.limit !== undefined) params.set('limit', String(filters.limit));
  if (filters.offset !== undefined) params.set('offset', String(filters.offset));
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

export async function createNote(data: NoteCreate): Promise<NoteOut> {
  return apiPost<NoteOut>('/api/notes', data);
}

export async function listNotes(filters: NotesListFilters = {}): Promise<NotesListResponse> {
  return apiGet<NotesListResponse>(`/api/notes${buildQuery(filters)}`);
}

export async function getNote(id: string): Promise<NoteOut> {
  return apiGet<NoteOut>(`/api/notes/${id}`);
}

export async function updateNote(id: string, patch: NoteUpdate): Promise<NoteOut> {
  return apiPut<NoteOut>(`/api/notes/${id}`, patch);
}

export async function deleteNote(id: string): Promise<void> {
  return apiDelete(`/api/notes/${id}`);
}

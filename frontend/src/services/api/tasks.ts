import { apiGet, apiPatch, apiPost } from '../../api/client';
import type { NoteOut } from '../../api/notes';

export interface Task {
  id: string;
  title: string | null;
  content: string;
  due_at: string | null;
  priority: 1 | 2 | 3 | null;
  recurring: 'daily' | 'weekly' | 'monthly' | null;
  done_at: string | null;
  category: string;
  created_at: string;
  updated_at: string;
}

export interface TaskListResponse {
  items: Task[];
  total: number;
}

export type TaskStatus = 'open' | 'overdue' | 'done' | 'all';

export interface TaskListOptions {
  status?: TaskStatus;
  priority?: 1 | 2 | 3;
  limit?: number;
  offset?: number;
}

export interface TaskNoteUpdate {
  due_at?: string | null;
  done_at?: string | null;
  priority?: 1 | 2 | 3 | null;
  recurring?: 'daily' | 'weekly' | 'monthly' | null;
  reminder_sent_at?: string | null;
}

function buildQuery(opts: TaskListOptions): string {
  const params = new URLSearchParams();
  if (opts.status) params.set('status', opts.status);
  if (opts.priority !== undefined) params.set('priority', String(opts.priority));
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  if (opts.offset !== undefined) params.set('offset', String(opts.offset));
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

export async function listTasks(opts: TaskListOptions = {}): Promise<TaskListResponse> {
  return apiGet<TaskListResponse>(`/api/tasks${buildQuery(opts)}`);
}

export async function toggleDone(noteId: string): Promise<NoteOut> {
  return apiPost<NoteOut>(`/api/notes/${encodeURIComponent(noteId)}/done`);
}

export async function updateNote(noteId: string, changes: TaskNoteUpdate): Promise<NoteOut> {
  return apiPatch<NoteOut>(`/api/notes/${encodeURIComponent(noteId)}`, changes);
}

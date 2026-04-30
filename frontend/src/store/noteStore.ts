import { create } from 'zustand';
import type { NoteOut } from '../api/notes';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NoteState {
  /** In-memory cache of notes (loaded from server or IndexedDB) */
  notes: NoteOut[];
  /** Whether notes are currently being loaded */
  isLoading: boolean;
  /** Last load error, if any */
  error: string | null;

  // Actions
  loadNotes: (notes: NoteOut[]) => void;
  addNote: (note: NoteOut) => void;
  updateNote: (id: string, patch: Partial<NoteOut>) => void;
  removeNote: (id: string) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useNoteStore = create<NoteState>()((set) => ({
  notes: [],
  isLoading: false,
  error: null,

  loadNotes: (notes) => set({ notes, isLoading: false, error: null }),

  addNote: (note) =>
    set((state) => ({
      notes: [note, ...state.notes],
    })),

  updateNote: (id, patch) =>
    set((state) => ({
      notes: state.notes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
    })),

  removeNote: (id) =>
    set((state) => ({
      notes: state.notes.filter((n) => n.id !== id),
    })),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),
}));

import { create } from 'zustand';
import type { Category } from '../api/notes';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ModalType =
  | 'none'
  | 'create-note'
  | 'delete-confirm'
  | 'conflict-resolution'
  | 'note-detail';

interface UIState {
  /** Global loading overlay flag */
  isLoading: boolean;
  /** Currently open modal */
  currentModal: ModalType;
  /** Payload for the current modal (e.g. note id for delete-confirm) */
  modalPayload: unknown;
  /** Category filter applied to the library view */
  selectedCategory: Category | null;

  // Actions
  setLoading: (isLoading: boolean) => void;
  openModal: (modal: ModalType, payload?: unknown) => void;
  closeModal: () => void;
  setSelectedCategory: (category: Category | null) => void;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useUIStore = create<UIState>()((set) => ({
  isLoading: false,
  currentModal: 'none',
  modalPayload: null,
  selectedCategory: null,

  setLoading: (isLoading) => set({ isLoading }),

  openModal: (modal, payload = null) =>
    set({ currentModal: modal, modalPayload: payload }),

  closeModal: () => set({ currentModal: 'none', modalPayload: null }),

  setSelectedCategory: (category) => set({ selectedCategory: category }),
}));

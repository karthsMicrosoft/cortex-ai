/**
 * PersonalDictionary component.
 *
 * Displays the user's vocabulary terms as color-coded chips grouped by type.
 * Provides controlled input + type selector + add button + instant delete.
 * Includes a bulk CSV/JSON import affordance.
 *
 * Design spec: addendum F1.2 / task 4.2.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Mic, Plus, X } from 'lucide-react';
import {
  addTerm,
  bulkImport,
  deleteTerm,
  listTerms,
  type TermType,
  type VocabularyTermCreate,
  type VocabularyTermOut,
} from '../api/dictionary';
import { ApiError } from '../api/client';

// ---------------------------------------------------------------------------
// Type colors — per design spec F1.2
// ---------------------------------------------------------------------------

const TYPE_COLORS: Record<TermType, string> = {
  name: 'bg-blue-900 text-blue-100',
  music_term: 'bg-purple-900 text-purple-100',
  technical: 'bg-green-900 text-green-100',
  place: 'bg-amber-900 text-amber-100',
  acronym: 'bg-rose-900 text-rose-100',
  general: 'bg-slate-700 text-slate-200',
};

const TYPE_LABELS: Record<TermType, string> = {
  name: 'Name',
  music_term: 'Music',
  technical: 'Technical',
  place: 'Place',
  acronym: 'Acronym',
  general: 'General',
};

const ALL_TYPES: TermType[] = ['general', 'name', 'music_term', 'technical', 'place', 'acronym'];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PersonalDictionary(): React.ReactElement {
  const [terms, setTerms] = useState<VocabularyTermOut[]>([]);
  const [newTerm, setNewTerm] = useState('');
  const [newType, setNewType] = useState<TermType>('general');
  const [filter, setFilter] = useState<TermType | ''>('');
  const [error, setError] = useState<string | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---------------------------------------------------------------------------
  // Load terms
  // ---------------------------------------------------------------------------

  const loadTerms = useCallback(async () => {
    try {
      const data = await listTerms(filter ? { term_type: filter } : undefined);
      setTerms(data);
    } catch {
      // Silently fail — list remains as-is
    }
  }, [filter]);

  useEffect(() => {
    void loadTerms();
  }, [loadTerms]);

  // ---------------------------------------------------------------------------
  // Add term
  // ---------------------------------------------------------------------------

  const handleAdd = useCallback(async () => {
    const trimmed = newTerm.trim();
    if (!trimmed) return;
    setIsAdding(true);
    setError(null);
    try {
      await addTerm({ term: trimmed, term_type: newType });
      setNewTerm('');
      await loadTerms();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setError('That term already exists in your dictionary.');
        } else if (err.status === 400) {
          setError('You have reached the 2,000 term limit. Delete some terms first.');
        } else {
          setError(err.detail || 'Failed to add term.');
        }
      } else {
        setError('Failed to add term. Please try again.');
      }
    } finally {
      setIsAdding(false);
    }
  }, [newTerm, newType, loadTerms]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      void handleAdd();
    }
  };

  // ---------------------------------------------------------------------------
  // Delete term
  // ---------------------------------------------------------------------------

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await deleteTerm(id);
        await loadTerms();
      } catch {
        setError('Failed to delete term. Please try again.');
      }
    },
    [loadTerms],
  );

  // ---------------------------------------------------------------------------
  // Bulk import (CSV / JSON)
  // ---------------------------------------------------------------------------

  const handleFileImport = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setIsImporting(true);
      setError(null);

      try {
        const text = await file.text();
        let termPayloads: VocabularyTermCreate[] = [];

        if (file.name.endsWith('.json')) {
          const parsed = JSON.parse(text) as unknown;
          if (!Array.isArray(parsed)) {
            throw new Error('JSON file must be an array of term objects.');
          }
          termPayloads = (parsed as VocabularyTermCreate[]).map((item) => ({
            term: String((item as Record<string, unknown>).term ?? ''),
            term_type:
              ((item as Record<string, unknown>).term_type as TermType | undefined) ?? 'general',
            pronunciation_hint:
              ((item as Record<string, unknown>).pronunciation_hint as string | undefined) ?? null,
            boost_weight:
              ((item as Record<string, unknown>).boost_weight as number | undefined) ?? 1.0,
          }));
        } else {
          // CSV: one term per line; optional second column for term_type
          const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
          termPayloads = lines.map((line) => {
            const [term, term_type] = line.split(',').map((s) => s.trim());
            return {
              term,
              term_type: (ALL_TYPES.includes(term_type as TermType) ? term_type : 'general') as TermType,
            };
          });
        }

        // Filter out empties
        termPayloads = termPayloads.filter((t) => t.term);

        // Chunk into ≤500 per request
        const CHUNK = 500;
        for (let i = 0; i < termPayloads.length; i += CHUNK) {
          await bulkImport(termPayloads.slice(i, i + CHUNK));
        }

        await loadTerms();
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.detail || 'Import failed.');
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError('Import failed. Check your file format and try again.');
        }
      } finally {
        setIsImporting(false);
        // Reset file input so same file can be re-selected
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      }
    },
    [loadTerms],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const filtered = filter ? terms.filter((t) => t.term_type === filter) : terms;

  return (
    <section className="bg-slate-900 rounded-2xl p-6">
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <Mic className="w-5 h-5 text-indigo-400" />
        <h2 className="text-xl font-semibold text-white">Personal Dictionary</h2>
        <span className="ml-auto text-xs text-slate-500">{terms.length} / 2000 terms</span>
      </div>
      <p className="text-slate-400 text-sm mb-4">
        Add names, jargon, or terms you use often to improve voice transcription accuracy.
      </p>

      {/* Error banner */}
      {error && (
        <div className="mb-3 rounded-lg bg-red-900/50 border border-red-700 px-4 py-2 text-sm text-red-200 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-200">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Add term row */}
      <div className="flex gap-2 mb-4">
        <input
          value={newTerm}
          onChange={(e) => setNewTerm(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="e.g. Phrygian mode, Karthik, pgvector"
          className="flex-1 bg-slate-800 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-600"
          disabled={isAdding}
          aria-label="New term"
        />
        <select
          value={newType}
          onChange={(e) => setNewType(e.target.value as TermType)}
          className="bg-slate-800 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-600"
          disabled={isAdding}
          aria-label="Term type"
        >
          {ALL_TYPES.map((t) => (
            <option key={t} value={t}>
              {TYPE_LABELS[t]}
            </option>
          ))}
        </select>
        <button
          onClick={() => void handleAdd()}
          disabled={isAdding || !newTerm.trim()}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed px-3 rounded-lg transition-colors"
          aria-label="Add term"
        >
          <Plus className="w-4 h-4 text-white" />
        </button>
      </div>

      {/* Type filter chips */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button
          onClick={() => setFilter('')}
          className={`px-3 py-1 rounded-full text-xs transition-colors ${
            filter === ''
              ? 'bg-indigo-700 text-white'
              : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
          }`}
        >
          All
        </button>
        {ALL_TYPES.map((t) => (
          <button
            key={t}
            onClick={() => setFilter(filter === t ? '' : t)}
            className={`px-3 py-1 rounded-full text-xs transition-colors ${
              filter === t
                ? `${TYPE_COLORS[t]} ring-2 ring-white/30`
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
            }`}
          >
            {TYPE_LABELS[t]}
          </button>
        ))}
      </div>

      {/* Term chips */}
      <div className="flex flex-wrap gap-2 mb-4 min-h-[2rem]">
        {filtered.length === 0 ? (
          <p className="text-slate-600 text-sm italic">No terms yet. Add one above.</p>
        ) : (
          filtered.map((t) => (
            <span
              key={t.id}
              className={`${TYPE_COLORS[t.term_type]} pl-3 pr-1 py-1 rounded-full text-xs flex items-center gap-1`}
            >
              {t.term}
              <button
                onClick={() => void handleDelete(t.id)}
                className="hover:bg-black/20 rounded-full p-0.5 transition-colors"
                aria-label={`Remove ${t.term}`}
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))
        )}
      </div>

      {/* Bulk import */}
      <div className="flex items-center gap-3 pt-3 border-t border-slate-800">
        <span className="text-xs text-slate-500">Import CSV or JSON:</span>
        <label
          className={`cursor-pointer text-xs text-indigo-400 hover:text-indigo-300 transition-colors ${isImporting ? 'opacity-50 pointer-events-none' : ''}`}
        >
          {isImporting ? 'Importing…' : 'Choose file'}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.json"
            className="sr-only"
            onChange={(e) => void handleFileImport(e)}
            disabled={isImporting}
            data-testid="bulk-import-input"
          />
        </label>
        <span className="text-xs text-slate-600">
          CSV: one term per line, optional ",type" column. JSON: array of{' '}
          <code className="text-slate-500">{'{"term":"...","term_type":"..."}'}</code>
        </span>
      </div>
    </section>
  );
}

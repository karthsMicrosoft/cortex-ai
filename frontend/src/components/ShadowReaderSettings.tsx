/**
 * ShadowReaderSettings — settings section for the Shadow Reader feature (US-8).
 *
 * Renders:
 *  - Global enable/disable checkbox
 *  - Per-category opt-out chips (toggling adds/removes from disabledCategories)
 *  - Save button that calls PUT /api/users/me/shadow-reader/settings
 *
 * On mount, loads the current user's shadow reader settings from GET /api/auth/me
 * (the UserOut schema exposes shadow_reader_enabled / shadow_reader_disabled_categories).
 */

import { useEffect, useState } from 'react';
import { BookOpen } from 'lucide-react';
import { updateSettings } from '../api/shadowReader';
import { apiGet } from '../api/client';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ALL_CATEGORIES = ['Music', 'Fitness', 'Journal', 'Ideas', 'Spiritual', 'Learning'] as const;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UserSettingsOut {
  shadow_reader_enabled?: boolean;
  shadow_reader_disabled_categories?: string[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ShadowReaderSettings(): React.ReactElement {
  const [enabled, setEnabled] = useState(true);
  const [disabledCategories, setDisabledCategories] = useState<string[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Load current settings from /api/auth/me on mount
  useEffect(() => {
    void (async () => {
      try {
        const user = await apiGet<UserSettingsOut>('/api/auth/me');
        if (typeof user.shadow_reader_enabled === 'boolean') {
          setEnabled(user.shadow_reader_enabled);
        }
        if (Array.isArray(user.shadow_reader_disabled_categories)) {
          setDisabledCategories(user.shadow_reader_disabled_categories);
        }
      } catch {
        // Non-critical — use defaults
      }
    })();
  }, []);

  const toggleCategory = (cat: string) => {
    setDisabledCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat],
    );
    setSaveSuccess(false);
  };

  const handleSave = async () => {
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(false);
    try {
      await updateSettings({ enabled, disabled_categories: disabledCategories });
      setSaveSuccess(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <section className="bg-slate-900 rounded-2xl p-6" aria-label="Shadow Reader settings">
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <BookOpen className="w-5 h-5 text-indigo-400" aria-hidden="true" />
        <h2 className="text-xl font-semibold">Shadow Reader</h2>
      </div>
      <p className="text-slate-400 text-sm mb-4">
        After capture, get gentle questions that help you go deeper into your thinking.
      </p>

      {/* Global toggle */}
      <label className="flex items-center justify-between mb-4 cursor-pointer">
        <span className="text-sm text-slate-200">Enable Shadow Reader</span>
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => {
            setEnabled(e.target.checked);
            setSaveSuccess(false);
          }}
          className="w-5 h-5 rounded accent-indigo-500 cursor-pointer"
          aria-label="Enable Shadow Reader globally"
        />
      </label>

      {/* Per-category opt-outs */}
      {enabled && (
        <>
          <p className="text-xs text-slate-500 mb-2">Skip questions for these categories:</p>
          <div className="flex flex-wrap gap-2 mb-4" role="group" aria-label="Category opt-outs">
            {ALL_CATEGORIES.map((cat) => {
              const isDisabled = disabledCategories.includes(cat);
              return (
                <button
                  key={cat}
                  type="button"
                  onClick={() => toggleCategory(cat)}
                  className={[
                    'px-3 py-1 rounded-full text-xs transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-400',
                    isDisabled
                      ? 'bg-slate-700 line-through text-slate-500'
                      : 'bg-indigo-900 text-indigo-200 hover:bg-indigo-800',
                  ].join(' ')}
                  aria-pressed={isDisabled}
                  aria-label={`${isDisabled ? 'Re-enable' : 'Disable'} Shadow Reader for ${cat}`}
                >
                  {cat}
                </button>
              );
            })}
          </div>
        </>
      )}

      {/* Save */}
      {saveError && (
        <p className="text-xs text-red-400 mb-2" role="alert">
          {saveError}
        </p>
      )}
      {saveSuccess && (
        <p className="text-xs text-green-400 mb-2" role="status">
          Settings saved.
        </p>
      )}
      <button
        type="button"
        onClick={() => void handleSave()}
        disabled={isSaving}
        className="bg-indigo-600 px-4 py-2 rounded-lg text-sm text-white hover:bg-indigo-500 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-indigo-400"
      >
        {isSaving ? 'Saving…' : 'Save'}
      </button>
    </section>
  );
}

/**
 * SettingsPage — top-level settings surface.
 *
 * Hosts the PersonalDictionary section (US-7).
 * US-8 will append ShadowReaderSettings below PersonalDictionary.
 *
 * Accessed via gear icon in the app header (no bottom-nav slot).
 */
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Settings } from 'lucide-react';
import { PersonalDictionary } from '../components/PersonalDictionary';

export default function SettingsPage(): React.ReactElement {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#0F172A] text-white">
      {/* Header */}
      <header className="flex items-center gap-3 px-4 py-4 border-b border-slate-800">
        <button
          onClick={() => navigate(-1)}
          className="p-2 rounded-lg hover:bg-slate-800 transition-colors"
          aria-label="Go back"
        >
          <ArrowLeft className="w-5 h-5 text-slate-400" />
        </button>
        <Settings className="w-5 h-5 text-indigo-400" />
        <h1 className="text-lg font-semibold">Settings</h1>
      </header>

      {/* Sections */}
      <main className="max-w-2xl mx-auto px-4 py-6 space-y-6">
        {/* Personal Dictionary — US-7 */}
        <PersonalDictionary />

        {/* ShadowReaderSettings — US-8 will append here */}
      </main>
    </div>
  );
}

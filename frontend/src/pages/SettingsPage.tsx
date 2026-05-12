/**
 * SettingsPage — top-level settings surface.
 *
 * Hosts the PersonalDictionary section (US-7) and ShadowReaderSettings (US-8),
 * plus a "Your Data" export action and an Account / change-password form
 * (Round 15 / PR #23 — promotes the password form from /profile so users find
 * it via the gear icon, while /profile remains for legacy bookmarks).
 *
 * Accessed via gear icon in the app header (no bottom-nav slot).
 */
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Settings, Download, Puzzle, Copy, LogOut } from 'lucide-react';
import { PersonalDictionary } from '../components/PersonalDictionary';
import { ShadowReaderSettings } from '../components/ShadowReaderSettings';
import { changePassword, mintClipToken } from '../api/auth';
import { downloadExport } from '../api/export';
import { useAuthStore } from '../store/authStore';

export default function SettingsPage(): React.ReactElement {
  const navigate = useNavigate();

  // ------------------------------------------------------------------ export
  const [exporting, setExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  async function handleExport(): Promise<void> {
    setExporting(true);
    setExportMessage(null);
    try {
      await downloadExport();
      setExportMessage({ kind: 'ok', text: 'Exported!' });
    } catch (err) {
      const text = err instanceof Error ? err.message : 'Export failed';
      setExportMessage({ kind: 'err', text });
    } finally {
      setExporting(false);
    }
  }

  // ------------------------------------------------------------------ password
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  // ------------------------------------------------------------------ sign-out
  const signOut = useAuthStore((s) => s.signOut);
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut(): Promise<void> {
    setSigningOut(true);
    try {
      await signOut();
      navigate('/login', { replace: true });
    } finally {
      setSigningOut(false);
    }
  }

  async function handlePasswordSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setPasswordMessage(null);
    if (newPassword.length < 8) {
      setPasswordMessage({ kind: 'err', text: 'New password must be at least 8 characters.' });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordMessage({ kind: 'err', text: 'Passwords do not match.' });
      return;
    }
    setPasswordSaving(true);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setPasswordMessage({ kind: 'ok', text: 'Password changed.' });
    } catch (err) {
      const text = err instanceof Error ? err.message : 'Password change failed';
      setPasswordMessage({ kind: 'err', text });
    } finally {
      setPasswordSaving(false);
    }
  }

  // ------------------------------------------------------------------ clip token (Round 19)
  // Token lives in component state only — never persisted to localStorage /
  // sessionStorage (it's a JWT — leakage risk).
  const [clipToken, setClipToken] = useState<string | null>(null);
  const [clipMinting, setClipMinting] = useState(false);
  const [clipError, setClipError] = useState<string | null>(null);
  const [clipCopied, setClipCopied] = useState(false);

  async function handleGenerateClipToken(): Promise<void> {
    setClipError(null);
    setClipCopied(false);
    setClipMinting(true);
    try {
      const res = await mintClipToken();
      setClipToken(res.clip_token);
    } catch (err) {
      const text = err instanceof Error ? err.message : 'Failed to generate clip token';
      setClipError(text);
    } finally {
      setClipMinting(false);
    }
  }

  async function handleCopyClipToken(): Promise<void> {
    if (!clipToken) return;
    try {
      await navigator.clipboard.writeText(clipToken);
      setClipCopied(true);
    } catch {
      setClipCopied(false);
    }
  }

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
        {/* Your Data — Round 15 / PR #23 */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-slate-200">Your Data</h2>
          <p className="text-xs text-slate-400">
            Download every note, summary, and dictionary term you've added to Cortex
            as a single JSON file. We never lock you in.
          </p>
          <button
            type="button"
            onClick={() => { void handleExport(); }}
            disabled={exporting}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            {exporting ? 'Exporting…' : 'Export your data'}
          </button>
          {exportMessage && (
            <p
              role={exportMessage.kind === 'err' ? 'alert' : 'status'}
              className={exportMessage.kind === 'err' ? 'text-xs text-red-400' : 'text-xs text-emerald-400'}
            >
              {exportMessage.text}
            </p>
          )}
        </section>

        {/* Account — Round 15 / PR #23 (mirrors ProfilePage form) */}
        <form
          onSubmit={(e) => { void handlePasswordSubmit(e); }}
          className="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3"
        >
          <h2 className="text-sm font-semibold text-slate-200">Account</h2>
          <p className="text-xs text-slate-400">Change your account password.</p>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder="Current password"
            autoComplete="current-password"
            required
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white"
            aria-label="Current password"
          />
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="New password (min 8 chars)"
            autoComplete="new-password"
            minLength={8}
            required
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white"
            aria-label="New password"
          />
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Confirm new password"
            autoComplete="new-password"
            minLength={8}
            required
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white"
            aria-label="Confirm new password"
          />
          {passwordMessage && (
            <p
              role={passwordMessage.kind === 'err' ? 'alert' : 'status'}
              className={passwordMessage.kind === 'err' ? 'text-xs text-red-400' : 'text-xs text-emerald-400'}
            >
              {passwordMessage.text}
            </p>
          )}
          <button
            type="submit"
            disabled={passwordSaving}
            className="w-full rounded-lg bg-indigo-600 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {passwordSaving ? 'Changing…' : 'Change password'}
          </button>
        </form>

        {/* Sign-out — Round 19 / PR A follow-up */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <LogOut className="h-4 w-4 text-rose-400" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-slate-200">Sign out</h2>
          </div>
          <p className="text-xs text-slate-400">
            Sign out of this device. Your refresh token will be revoked on the
            server, so other browsers will need to sign in again too.
          </p>
          <button
            type="button"
            data-testid="settings-sign-out"
            onClick={() => { void handleSignOut(); }}
            disabled={signingOut}
            className="w-full rounded-lg border border-rose-500/40 bg-rose-500/10 py-2 text-sm font-semibold text-rose-300 hover:bg-rose-500/20 disabled:opacity-50"
          >
            {signingOut ? 'Signing out…' : 'Sign out'}
          </button>
        </div>

        {/* Personal Dictionary — US-7 */}
        <PersonalDictionary />

        {/* Shadow Reader Settings — US-8 */}
        <ShadowReaderSettings />

        {/* Browser Extension — Round 19 / PR C */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Puzzle className="h-4 w-4 text-indigo-400" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-slate-200">Browser Extension</h2>
          </div>
          <p className="text-xs text-slate-400">
            Save any web page to Cortex with one click. Install the extension and
            paste the clip token below to authorize it.
          </p>
          <p className="text-[11px] text-slate-500">
            Load the unpacked extension from the <code>extension/</code> folder in
            your repo (Chrome → chrome://extensions → Developer mode → Load
            unpacked).
          </p>

          {clipError ? (
            <div className="space-y-2">
              <p role="alert" className="text-xs text-red-400">{clipError}</p>
              <button
                type="button"
                onClick={() => { void handleGenerateClipToken(); }}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-600 px-4 py-2 text-sm font-semibold text-slate-200 hover:border-slate-500 hover:text-white"
              >
                Retry
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => { void handleGenerateClipToken(); }}
              disabled={clipMinting}
              className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {clipMinting ? 'Generating…' : 'Generate clip token'}
            </button>
          )}

          {clipToken && !clipError ? (
            <div className="space-y-2">
              <code
                className="block w-full break-all rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-emerald-200"
                aria-label="Clip token"
              >
                {clipToken}
              </code>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => { void handleCopyClipToken(); }}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-600 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:border-slate-500 hover:text-white"
                >
                  <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  {clipCopied ? 'Copied' : 'Copy'}
                </button>
                <p className="text-[11px] text-slate-500">
                  Token expires in 30 days. Generate a new one to revoke this one.
                </p>
              </div>
            </div>
          ) : null}
        </section>
      </main>
    </div>
  );
}

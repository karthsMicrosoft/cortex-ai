import { useEffect, useState, type FormEvent } from 'react';
import { ArrowLeft, LogOut } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { changePassword, logout as logoutApi, me, updateProfile } from '../api/auth';

/**
 * ProfilePage — edit display name, change password, log out.
 *
 * Resolves three live-deploy gaps reported on 2026-05-01:
 *   • Issue #3a: no profile page to edit name/password
 *   • Issue #3b: no sign-out button
 *
 * Auth identity (email) is intentionally read-only — changing the auth email
 * needs a confirm-email flow that's out of MVP scope.
 */
export default function ProfilePage(): React.ReactElement {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);

  // ------------------------------------------------------------------ profile
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMessage, setProfileMessage] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  // Hydrate from API on mount in case store is stale
  useEffect(() => {
    let cancelled = false;
    me()
      .then((u) => {
        if (cancelled) return;
        setUser(u);
        setDisplayName(u.display_name ?? '');
      })
      .catch(() => {/* silent — auth restore will redirect if needed */});
    return () => { cancelled = true; };
  }, [setUser]);

  async function handleProfileSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setProfileSaving(true);
    setProfileMessage(null);
    try {
      const updated = await updateProfile(displayName.trim());
      setUser(updated);
      setProfileMessage({ kind: 'ok', text: 'Profile updated' });
    } catch (err) {
      const text = err instanceof Error ? err.message : 'Update failed';
      setProfileMessage({ kind: 'err', text });
    } finally {
      setProfileSaving(false);
    }
  }

  // ------------------------------------------------------------------ password
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

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

  // ------------------------------------------------------------------ logout
  async function handleLogout(): Promise<void> {
    try {
      await logoutApi();
    } catch {
      // Backend logout is best-effort — local logout still proceeds.
    }
    useAuthStore.getState().logout();
    navigate('/login', { replace: true });
  }

  // ------------------------------------------------------------------ render
  return (
    <div className="min-h-screen bg-[#0F172A] pb-24 text-white">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-slate-800 bg-[#0F172A]/95 px-4 py-3 backdrop-blur">
        <button
          type="button"
          aria-label="Back"
          onClick={() => navigate(-1)}
          className="rounded-md p-1 text-slate-300 hover:bg-slate-800"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <h1 className="text-lg font-semibold">Profile</h1>
      </header>

      <main className="mx-auto max-w-md space-y-6 p-4">
        {/* Account section ------------------------------------------------ */}
        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
          <h2 className="text-sm font-semibold text-slate-200">Account</h2>
          <dl className="mt-3 grid grid-cols-1 gap-2 text-sm">
            <div>
              <dt className="text-slate-400">Email</dt>
              <dd className="text-slate-100" data-testid="profile-email">{user?.email ?? '—'}</dd>
            </div>
          </dl>
        </section>

        {/* Display name --------------------------------------------------- */}
        <form
          onSubmit={(e) => { void handleProfileSubmit(e); }}
          className="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3"
        >
          <h2 className="text-sm font-semibold text-slate-200">Display name</h2>
          <input
            type="text"
            value={displayName}
            maxLength={100}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Your name"
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            aria-label="Display name"
          />
          {profileMessage && (
            <p
              role={profileMessage.kind === 'err' ? 'alert' : 'status'}
              className={profileMessage.kind === 'err' ? 'text-xs text-red-400' : 'text-xs text-emerald-400'}
            >
              {profileMessage.text}
            </p>
          )}
          <button
            type="submit"
            disabled={profileSaving}
            className="w-full rounded-lg bg-indigo-600 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {profileSaving ? 'Saving…' : 'Save'}
          </button>
        </form>

        {/* Change password ------------------------------------------------ */}
        <form
          onSubmit={(e) => { void handlePasswordSubmit(e); }}
          className="rounded-2xl border border-slate-800 bg-slate-900 p-4 space-y-3"
        >
          <h2 className="text-sm font-semibold text-slate-200">Change password</h2>
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

        {/* Sign out ------------------------------------------------------- */}
        <section className="rounded-2xl border border-red-900/50 bg-slate-900 p-4">
          <h2 className="text-sm font-semibold text-red-300">Sign out</h2>
          <p className="mt-1 text-xs text-slate-400">
            Revokes your refresh token and clears local session state.
          </p>
          <button
            type="button"
            onClick={() => { void handleLogout(); }}
            className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-red-700 bg-red-950/40 py-2 text-sm font-semibold text-red-200 hover:bg-red-900/60"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Sign out
          </button>
        </section>
      </main>
    </div>
  );
}

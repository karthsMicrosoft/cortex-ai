import { Link, useNavigate } from 'react-router-dom';
import { LogOut, UserCircle } from 'lucide-react';
import { useAuthStore } from '../store/authStore';

/**
 * AppHeader — minimal top bar with brand + profile shortcut + sign-out.
 *
 * Rendered inside the AuthGate so it appears on every authenticated page.
 * Right-side controls: Sign-out icon button + profile/settings link. The
 * bottom nav stays focused on the four primary tabs (Capture / Library /
 * Insights / Create) per spec § 2.6.
 */
export function AppHeader(): React.ReactElement {
  const user = useAuthStore((s) => s.user);
  const signOut = useAuthStore((s) => s.signOut);
  const navigate = useNavigate();
  const initial = (user?.display_name?.[0] ?? user?.email?.[0] ?? '?').toUpperCase();

  async function handleSignOut(): Promise<void> {
    await signOut();
    navigate('/login', { replace: true });
  }

  return (
    <header className="sticky top-0 z-30 flex h-12 items-center justify-between border-b border-slate-800 bg-[#0F172A]/95 px-4 backdrop-blur">
      <Link to="/" className="text-sm font-semibold text-indigo-400">
        Cortex
      </Link>
      <div className="flex items-center gap-2">
        {user ? (
          <button
            type="button"
            onClick={() => { void handleSignOut(); }}
            data-testid="header-sign-out"
            aria-label="Sign out"
            title="Sign out"
            className="flex h-8 w-8 items-center justify-center rounded-full text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
          </button>
        ) : null}
        <Link
          to="/settings"
          aria-label="Profile and settings"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800 text-sm font-semibold text-slate-200 hover:bg-slate-700"
        >
          {user ? initial : <UserCircle className="h-5 w-5" aria-hidden="true" />}
        </Link>
      </div>
    </header>
  );
}

export default AppHeader;

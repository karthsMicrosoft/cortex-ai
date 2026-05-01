import { Link } from 'react-router-dom';
import { UserCircle } from 'lucide-react';
import { useAuthStore } from '../store/authStore';

/**
 * AppHeader — minimal top bar with brand + profile shortcut.
 *
 * Rendered inside the AuthGate so it appears on every authenticated page.
 * Right-side button links to /profile (which contains edit-name, change-
 * password, and sign-out actions). The bottom nav stays focused on the four
 * primary tabs (Capture / Library / Insights / Create) per spec § 2.6.
 */
export function AppHeader(): React.ReactElement {
  const user = useAuthStore((s) => s.user);
  const initial = (user?.display_name?.[0] ?? user?.email?.[0] ?? '?').toUpperCase();

  return (
    <header className="sticky top-0 z-30 flex h-12 items-center justify-between border-b border-slate-800 bg-[#0F172A]/95 px-4 backdrop-blur">
      <Link to="/" className="text-sm font-semibold text-indigo-400">
        Cortex
      </Link>
      <Link
        to="/profile"
        aria-label="Profile and settings"
        className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800 text-sm font-semibold text-slate-200 hover:bg-slate-700"
      >
        {user ? initial : <UserCircle className="h-5 w-5" aria-hidden="true" />}
      </Link>
    </header>
  );
}

export default AppHeader;

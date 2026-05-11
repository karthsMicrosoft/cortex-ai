import { NavLink } from 'react-router-dom';
import { Mic, BookOpen, BarChart2, PenSquare, MessageCircle } from 'lucide-react';

// ---------------------------------------------------------------------------
// Tab config
// ---------------------------------------------------------------------------

const TABS = [
  { to: '/',         label: 'Capture',  Icon: Mic           },
  { to: '/library',  label: 'Library',  Icon: BookOpen      },
  { to: '/ask',      label: 'Ask',      Icon: MessageCircle },
  { to: '/insights', label: 'Insights', Icon: BarChart2     },
  { to: '/create',   label: 'Create',   Icon: PenSquare     },
] as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * BottomNav — fixed bottom navigation bar with five tabs.
 *
 * Uses react-router-dom NavLink so the active tab is automatically highlighted.
 * Visible on every authenticated page (rendered inside the protected layout).
 */
export function BottomNav(): React.ReactElement {
  return (
    <nav
      aria-label="Main navigation"
      className="fixed bottom-0 left-0 right-0 z-40 w-full flex h-16 items-stretch border-t border-slate-700 bg-slate-900/95 backdrop-blur-sm"
    >
      {TABS.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          aria-label={label}
          className={({ isActive }) =>
            [
              'flex flex-1 flex-col items-center justify-center gap-0.5 text-xs transition-colors',
              isActive
                ? 'text-indigo-400'
                : 'text-slate-500 hover:text-slate-300',
            ].join(' ')
          }
        >
          {({ isActive }) => (
            <>
              <Icon
                className={['h-5 w-5', isActive ? 'text-indigo-400' : ''].join(' ')}
                aria-hidden="true"
              />
              <span>{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

export default BottomNav;

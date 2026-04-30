import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './store/authStore';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import CapturePage from './pages/CapturePage';
import LibraryPage from './pages/LibraryPage';
import SearchPage from './pages/SearchPage';
import NoteDetailPage from './pages/NoteDetailPage';
import InsightsPage from './pages/InsightsPage';
// PERF-10: lazy-load BrainViewPage so react-force-graph-2d (d3 + canvas) is
// code-split into its own chunk and does not bloat the initial JS bundle.
const BrainViewPage = lazy(() => import('./pages/BrainViewPage'));
import CreatePage from './pages/CreatePage';
import ConflictsPage from './pages/ConflictsPage';
import SettingsPage from './pages/SettingsPage';  // US-7
import { BottomNav } from './components/BottomNav';

// ---------------------------------------------------------------------------
// Protected layout — AuthGate + BottomNav
// ---------------------------------------------------------------------------

function AuthGate({ children }: { children: React.ReactNode }): React.ReactElement {
  const accessToken = useAuthStore((s) => s.accessToken);
  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }
  return (
    <>
      {children}
      <BottomNav />
    </>
  );
}

// ---------------------------------------------------------------------------
// App — route table
// ---------------------------------------------------------------------------

export default function App(): React.ReactElement {
  return (
    <div className="min-h-screen bg-[#0F172A]">
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* Protected routes */}
        <Route
          path="/"
          element={
            <AuthGate>
              <CapturePage />
            </AuthGate>
          }
        />
        <Route
          path="/library"
          element={
            <AuthGate>
              <LibraryPage />
            </AuthGate>
          }
        />
        <Route
          path="/search"
          element={
            <AuthGate>
              <SearchPage />
            </AuthGate>
          }
        />
        <Route
          path="/note/:id"
          element={
            <AuthGate>
              <NoteDetailPage />
            </AuthGate>
          }
        />
        <Route
          path="/insights"
          element={
            <AuthGate>
              <InsightsPage />
            </AuthGate>
          }
        />
        <Route
          path="/brain"
          element={
            <AuthGate>
              {/* PERF-10: Suspense boundary for lazy BrainViewPage chunk */}
              <Suspense fallback={
                <div className="flex min-h-screen items-center justify-center bg-[#0F172A]">
                  <span className="text-sm text-slate-400">Loading brain view…</span>
                </div>
              }>
                <BrainViewPage />
              </Suspense>
            </AuthGate>
          }
        />
        <Route
          path="/create"
          element={
            <AuthGate>
              <CreatePage />
            </AuthGate>
          }
        />
        <Route
          path="/conflicts"
          element={
            <AuthGate>
              <ConflictsPage />
            </AuthGate>
          }
        />
        <Route
          path="/settings"
          element={
            <AuthGate>
              <SettingsPage />
            </AuthGate>
          }
        />

        {/* Wildcard: redirect unknown paths */}
        <Route
          path="*"
          element={
            <AuthGate>
              <Navigate to="/" replace />
            </AuthGate>
          }
        />
      </Routes>
    </div>
  );
}

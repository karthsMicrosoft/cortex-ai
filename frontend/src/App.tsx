import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './store/authStore';
// Eager imports — auth boundary + first-paint pages must render immediately
// (no extra round-trip for the chunk download).
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import CapturePage from './pages/CapturePage';
import ConflictsPage from './pages/ConflictsPage';
import ProfilePage from './pages/ProfilePage';   // 2026-05-01 — issue #3

// PERF (Round 15 / PR #25): code-split secondary pages so the initial JS
// bundle stays small. PERF-10 already lazy-loaded BrainViewPage; this round
// adds Insights / Create / Settings / NoteDetail / Library / Search.
const BrainViewPage = lazy(() => import('./pages/BrainViewPage'));
const InsightsPage = lazy(() => import('./pages/InsightsPage'));
const CreatePage = lazy(() => import('./pages/CreatePage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));  // US-7
const NoteDetailPage = lazy(() => import('./pages/NoteDetailPage'));
const LibraryPage = lazy(() => import('./pages/LibraryPage'));
const SearchPage = lazy(() => import('./pages/SearchPage'));
const AskPage = lazy(() => import('./pages/AskPage'));
const SharePage = lazy(() => import('./pages/SharePage'));

import { BottomNav } from './components/BottomNav';
import { AppHeader } from './components/AppHeader';
import { SessionGate } from './components/SessionGate';
import { RouteLoading } from './components/RouteLoading';

// ---------------------------------------------------------------------------
// Protected layout — AuthGate + AppHeader + BottomNav
// ---------------------------------------------------------------------------

function AuthGate({ children }: { children: React.ReactNode }): React.ReactElement {
  const accessToken = useAuthStore((s) => s.accessToken);
  const isRestoring = useAuthStore((s) => s.isRestoring);

  // While SessionGate is still attempting refresh on first boot, render
  // nothing — SessionGate itself shows the splash.
  if (isRestoring && !accessToken) {
    return <></>;
  }
  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }
  return (
    <>
      <AppHeader />
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
      <SessionGate>
      <Suspense fallback={<RouteLoading />}>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        {/* Phase 5 / PR 5.1 — /share is PUBLIC so the OS share sheet can land
            here whether or not the user is logged in. SharePage stashes the
            payload + redirects to /login when accessToken is null. */}
        <Route path="/share" element={<SharePage />} />

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
              {/* PERF-10: lazy BrainViewPage chunk; Suspense boundary lives at
                  the routing layer (single fallback for all lazy routes). */}
              <BrainViewPage />
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
          path="/ask"
          element={
            <AuthGate>
              <AskPage />
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
        <Route
          path="/profile"
          element={
            <AuthGate>
              <ProfilePage />
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
      </Suspense>
      </SessionGate>
    </div>
  );
}

import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './store/authStore';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';

// ---------------------------------------------------------------------------
// AuthGate — redirects unauthenticated users to /login
// ---------------------------------------------------------------------------

function AuthGate({ children }: { children: React.ReactNode }): React.ReactElement {
  const accessToken = useAuthStore((s) => s.accessToken);
  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// Placeholder pages for protected routes (to be implemented in later stories)
// ---------------------------------------------------------------------------

function CapturePage(): React.ReactElement {
  return <div className="p-4 text-slate-100">Capture</div>;
}

function LibraryPage(): React.ReactElement {
  return <div className="p-4 text-slate-100">Library</div>;
}

function InsightsPage(): React.ReactElement {
  return <div className="p-4 text-slate-100">Insights</div>;
}

function CreatePage(): React.ReactElement {
  return <div className="p-4 text-slate-100">Create</div>;
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
          path="/insights"
          element={
            <AuthGate>
              <InsightsPage />
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

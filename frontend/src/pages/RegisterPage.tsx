import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register as registerApi, login as loginApi, me } from '../api/auth';
import { useAuthStore } from '../store/authStore';

export default function RegisterPage(): React.ReactElement {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Use the hook so the mock in tests works correctly
  const { login } = useAuthStore();
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      // Register the account (pass displayName even if empty so callers can detect it)
      await registerApi(email, password, displayName);
      // Auto-login after successful registration
      const data = await loginApi(email, password);
      // Store the access token BEFORE calling me() so the Bearer header is attached
      useAuthStore.getState().setAccessToken(data.access_token);
      const user = await me();
      login(data.access_token, user);
      navigate('/', { replace: true });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Registration failed. Please try again.';
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0F172A] flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white">Cortex</h1>
          <p className="text-slate-400 mt-2">Create your account</p>
        </div>

        <form
          onSubmit={(e) => { void handleSubmit(e); }}
          className="bg-slate-800 rounded-2xl p-6 space-y-4"
        >
          <h2 className="text-xl font-semibold text-white">Register</h2>

          {error && (
            <div
              role="alert"
              className="bg-red-900/40 border border-red-500 text-red-300 rounded-lg p-3 text-sm"
            >
              {error}
            </div>
          )}

          <div>
            <label htmlFor="display-name" className="block text-sm font-medium text-slate-300 mb-1">
              Display name <span className="text-slate-500">(optional)</span>
            </label>
            <input
              id="display-name"
              type="text"
              autoComplete="name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="Your name"
            />
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-300 mb-1">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-300 mb-1">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full bg-[#4F46E5] hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg py-2 px-4 transition-colors"
          >
            {isSubmitting ? 'Creating account…' : 'Create account'}
          </button>

          <p className="text-center text-sm text-slate-400">
            Already have an account?{' '}
            <Link to="/login" className="text-indigo-400 hover:text-indigo-300 font-medium">
              Sign in
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}

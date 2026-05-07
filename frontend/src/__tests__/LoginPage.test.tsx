/**
 * Task 5.3 (LoginPage) — TDD red
 *
 * Tests that pages/LoginPage.tsx:
 *   - Renders email + password inputs and a submit button
 *   - On submit calls auth.login(email, password)
 *   - On success stores token in authStore and navigates to /
 *   - On error shows error message
 *   - Disables submit while in flight
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// ----- Mock auth store -----
// The api/client.ts retry-on-401 path calls useAuthStore.getState(), so the
// mock must expose getState() in addition to the hook callable form. Older
// versions of this test only mocked the hook (vi.fn(() => ({...}))), which
// caused 'useAuthStore.getState is not a function' to bubble up from any
// /api call the page made.
const mockLogin = vi.fn();
const _loginPageAuthState = {
  accessToken: null,
  user: null,
  login: mockLogin,
  logout: vi.fn(),
  setAccessToken: vi.fn(),
};
vi.mock('../store/authStore', () => ({
  useAuthStore: Object.assign(
    vi.fn(() => _loginPageAuthState),
    {
      getState: () => _loginPageAuthState,
      subscribe: () => () => {},
      setState: () => {},
    },
  ),
}));

// ----- Mock auth API -----
vi.mock('../api/auth', () => ({
  login: vi.fn(),
  me: vi.fn(),
}));

import LoginPage from '../pages/LoginPage';
import { login as loginApi, me as meApi } from '../api/auth';
import { useAuthStore } from '../store/authStore';

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------
function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div data-testid="home-page">Home</div>} />
        <Route path="/register" element={<div data-testid="register-page">Register</div>} />
      </Routes>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Helpers to grab inputs
// ---------------------------------------------------------------------------
function getEmailInput() {
  return (
    document.querySelector<HTMLInputElement>('input[type="email"]') ??
    document.querySelector<HTMLInputElement>('input[name="email"]')
  );
}
function getPasswordInput() {
  return document.querySelector<HTMLInputElement>('input[type="password"]');
}
function getSubmitButton() {
  return screen.getByRole('button', { name: /login|sign in|log in/i });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('LoginPage (Task 5.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- Render ---

  it('renders an email input', () => {
    renderLoginPage();
    expect(getEmailInput()).toBeTruthy();
  });

  it('renders a password input', () => {
    renderLoginPage();
    expect(getPasswordInput()).toBeTruthy();
  });

  it('renders a Login / Sign in submit button', () => {
    renderLoginPage();
    expect(getSubmitButton()).toBeTruthy();
  });

  it('renders a link to the register page', () => {
    renderLoginPage();
    const link = screen.getByRole('link', { name: /register|sign up|create account/i });
    expect(link).toBeTruthy();
  });

  // --- Submit flow ---

  it('calls auth.login() with email and password on submit', async () => {
    vi.mocked(loginApi).mockResolvedValueOnce({
      access_token: 'tok-123',
      token_type: 'bearer',
    });
    vi.mocked(meApi).mockResolvedValueOnce({
      id: 'u1',
      email: 'test@example.com',
      display_name: 'Test',
    });

    renderLoginPage();
    fireEvent.change(getEmailInput()!, { target: { value: 'test@example.com' } });
    fireEvent.change(getPasswordInput()!, { target: { value: 'secret123' } });
    fireEvent.click(getSubmitButton());

    await waitFor(() => {
      expect(loginApi).toHaveBeenCalledWith('test@example.com', 'secret123');
    });
  });

  it('calls authStore.login() with access token and user after successful login', async () => {
    vi.mocked(loginApi).mockResolvedValueOnce({
      access_token: 'tok-success',
      token_type: 'bearer',
    });
    vi.mocked(meApi).mockResolvedValueOnce({
      id: 'u2',
      email: 'alice@example.com',
      display_name: 'Alice',
    });

    renderLoginPage();
    fireEvent.change(getEmailInput()!, { target: { value: 'alice@example.com' } });
    fireEvent.change(getPasswordInput()!, { target: { value: 'pass' } });
    fireEvent.click(getSubmitButton());

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith(
        'tok-success',
        expect.objectContaining({ email: 'alice@example.com' })
      );
    });
  });

  it('navigates to / after successful login', async () => {
    vi.mocked(loginApi).mockResolvedValueOnce({
      access_token: 'tok-nav',
      token_type: 'bearer',
    });
    vi.mocked(meApi).mockResolvedValueOnce({
      id: 'u3',
      email: 'nav@example.com',
      display_name: 'Nav',
    });

    renderLoginPage();
    fireEvent.change(getEmailInput()!, { target: { value: 'nav@example.com' } });
    fireEvent.change(getPasswordInput()!, { target: { value: 'navpass' } });
    fireEvent.click(getSubmitButton());

    await waitFor(() => {
      expect(screen.getByTestId('home-page')).toBeTruthy();
    });
  });

  // --- Error handling ---

  it('displays error message on login failure', async () => {
    vi.mocked(loginApi).mockRejectedValueOnce(
      Object.assign(new Error('Invalid credentials'), {
        detail: 'Invalid credentials',
        code: 'invalid_credentials',
        status: 401,
      })
    );

    renderLoginPage();
    fireEvent.change(getEmailInput()!, { target: { value: 'bad@example.com' } });
    fireEvent.change(getPasswordInput()!, { target: { value: 'wrongpass' } });
    fireEvent.click(getSubmitButton());

    await waitFor(() => {
      const body = document.body.textContent?.toLowerCase() ?? '';
      const hasErrorText =
        body.includes('invalid') ||
        body.includes('error') ||
        body.includes('credentials') ||
        body.includes('wrong') ||
        body.includes('failed');
      expect(hasErrorText).toBe(true);
    });
  });

  // --- Loading state ---

  it('disables submit button while the login request is in flight', async () => {
    vi.mocked(loginApi).mockImplementationOnce(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                access_token: 't',
                token_type: 'bearer' as const,
              }),
            200
          )
        )
    );
    vi.mocked(meApi).mockResolvedValueOnce({
      id: 'u',
      email: 'e@e.com',
      display_name: 'E',
    });

    renderLoginPage();
    fireEvent.change(getEmailInput()!, { target: { value: 'e@e.com' } });
    fireEvent.change(getPasswordInput()!, { target: { value: 'pass' } });

    const btn = getSubmitButton() as HTMLButtonElement;
    fireEvent.click(btn);

    // Immediately after click, button should be disabled
    expect(btn.disabled).toBe(true);
  });
});

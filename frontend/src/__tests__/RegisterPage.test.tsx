/**
 * Task 5.4 (RegisterPage) — TDD red
 *
 * Tests that pages/RegisterPage.tsx:
 *   - Renders email, password inputs + optional displayName + submit button
 *   - On submit calls auth.register(email, password, displayName?)
 *   - After successful register calls auth.login() to auto-login
 *   - On success navigates to /
 *   - Shows server error messages
 *   - Disables submit while in flight
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// ----- Mock auth store -----
// Same pattern as LoginPage.test.tsx — api/client.ts:getState() needs to
// exist, otherwise pages that hit /api blow up with
// 'useAuthStore.getState is not a function'.
const mockLoginStore = vi.fn();
const _registerPageAuthState = {
  accessToken: null,
  user: null,
  login: mockLoginStore,
  logout: vi.fn(),
  setAccessToken: vi.fn(),
};
vi.mock('../store/authStore', () => ({
  useAuthStore: Object.assign(
    vi.fn(() => _registerPageAuthState),
    {
      getState: () => _registerPageAuthState,
      subscribe: () => () => {},
      setState: () => {},
    },
  ),
}));

// ----- Mock auth API -----
vi.mock('../api/auth', () => ({
  register: vi.fn(),
  login: vi.fn(),
  me: vi.fn(),
}));

import RegisterPage from '../pages/RegisterPage';
import { register as registerApi, login as loginApi, me as meApi } from '../api/auth';

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------
function renderRegisterPage() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/login" element={<div data-testid="login-page">Login</div>} />
        <Route path="/" element={<div data-testid="home-page">Home</div>} />
      </Routes>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Helpers
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
  return screen.getByRole('button', { name: /register|sign up|create account/i });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('RegisterPage (Task 5.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- Render ---

  it('renders an email input', () => {
    renderRegisterPage();
    expect(getEmailInput()).toBeTruthy();
  });

  it('renders a password input', () => {
    renderRegisterPage();
    expect(getPasswordInput()).toBeTruthy();
  });

  it('renders a Register / Sign up button', () => {
    renderRegisterPage();
    expect(getSubmitButton()).toBeTruthy();
  });

  it('renders a link to the login page', () => {
    renderRegisterPage();
    const link = screen.getByRole('link', { name: /login|sign in|already have/i });
    expect(link).toBeTruthy();
  });

  // --- Submit flow ---

  it('calls register API with email and password on submit', async () => {
    vi.mocked(registerApi).mockResolvedValueOnce({
      id: 'u-new',
      email: 'new@example.com',
      display_name: 'New User',
    });
    vi.mocked(loginApi).mockResolvedValueOnce({
      access_token: 'tok',
      token_type: 'bearer',
    });
    vi.mocked(meApi).mockResolvedValueOnce({
      id: 'u-new',
      email: 'new@example.com',
      display_name: 'New User',
    });

    renderRegisterPage();
    fireEvent.change(getEmailInput()!, { target: { value: 'new@example.com' } });
    fireEvent.change(getPasswordInput()!, { target: { value: 'password123' } });
    fireEvent.click(getSubmitButton());

    await waitFor(() => {
      expect(registerApi).toHaveBeenCalledWith(
        'new@example.com',
        'password123',
        expect.anything() // displayName may be undefined
      );
    });
  });

  it('logs in immediately after successful registration (Round-7: no separate /login call)', async () => {
    // Round-7 contract: /api/auth/register now returns access_token +
    // refresh_token in the body, so RegisterPage no longer makes a follow-up
    // loginApi call. It uses regData.access_token directly. See DECISIONS § 22v.
    vi.mocked(registerApi).mockResolvedValueOnce({
      id: 'u-autologin',
      email: 'auto@example.com',
      display_name: 'Auto',
      access_token: 'auto-tok',
      refresh_token: 'auto-refresh',
      token_type: 'bearer',
    });
    vi.mocked(meApi).mockResolvedValueOnce({
      id: 'u-autologin',
      email: 'auto@example.com',
      display_name: 'Auto',
    });

    renderRegisterPage();
    fireEvent.change(getEmailInput()!, { target: { value: 'auto@example.com' } });
    fireEvent.change(getPasswordInput()!, { target: { value: 'autopass' } });
    fireEvent.click(getSubmitButton());

    // The auth store's login() is called with the token from the register
    // response (no separate loginApi round-trip).
    await waitFor(() => {
      expect(mockLoginStore).toHaveBeenCalledWith(
        'auto-tok',
        expect.objectContaining({ email: 'auto@example.com' }),
      );
    });
    // Round-7 regression guard: loginApi must NOT have been called.
    expect(loginApi).not.toHaveBeenCalled();
  });

  it('calls authStore.login() with the token from the register response (Round-7)', async () => {
    // Round-7: register response itself carries access_token + refresh_token.
    vi.mocked(registerApi).mockResolvedValueOnce({
      id: 'u-store',
      email: 'store@example.com',
      display_name: 'Store',
      access_token: 'store-tok',
      refresh_token: 'store-refresh',
      token_type: 'bearer',
    });
    vi.mocked(meApi).mockResolvedValueOnce({
      id: 'u-store',
      email: 'store@example.com',
      display_name: 'Store',
    });

    renderRegisterPage();
    fireEvent.change(getEmailInput()!, { target: { value: 'store@example.com' } });
    fireEvent.change(getPasswordInput()!, { target: { value: 'storepass' } });
    fireEvent.click(getSubmitButton());

    await waitFor(() => {
      expect(mockLoginStore).toHaveBeenCalledWith(
        'store-tok',
        expect.objectContaining({ email: 'store@example.com' })
      );
    });
  });

  it('navigates to / after successful registration (Round-7: register response carries token)', async () => {
    vi.mocked(registerApi).mockResolvedValueOnce({
      id: 'u-nav',
      email: 'nav@example.com',
      display_name: 'Nav',
      access_token: 'nav-tok',
      refresh_token: 'nav-refresh',
      token_type: 'bearer',
    });
    vi.mocked(meApi).mockResolvedValueOnce({
      id: 'u-nav',
      email: 'nav@example.com',
      display_name: 'Nav',
    });

    renderRegisterPage();
    fireEvent.change(getEmailInput()!, { target: { value: 'nav@example.com' } });
    fireEvent.change(getPasswordInput()!, { target: { value: 'navpass' } });
    fireEvent.click(getSubmitButton());

    await waitFor(() => {
      expect(screen.getByTestId('home-page')).toBeTruthy();
    });
  });

  // --- Error handling ---

  it('shows error when email already exists (409)', async () => {
    vi.mocked(registerApi).mockRejectedValueOnce(
      Object.assign(new Error('Email already registered'), {
        detail: 'Email already registered',
        code: 'duplicate_email',
        status: 409,
      })
    );

    renderRegisterPage();
    fireEvent.change(getEmailInput()!, { target: { value: 'taken@example.com' } });
    fireEvent.change(getPasswordInput()!, { target: { value: 'any-pass' } });
    fireEvent.click(getSubmitButton());

    await waitFor(() => {
      const body = document.body.textContent?.toLowerCase() ?? '';
      const hasError =
        body.includes('already') ||
        body.includes('email') ||
        body.includes('error') ||
        body.includes('registered');
      expect(hasError).toBe(true);
    });
  });

  it('shows error message on 500 server error', async () => {
    vi.mocked(registerApi).mockRejectedValueOnce(
      Object.assign(new Error('Internal server error'), {
        detail: 'Internal server error',
        code: 'server_error',
        status: 500,
      })
    );

    renderRegisterPage();
    fireEvent.change(getEmailInput()!, { target: { value: 'err@example.com' } });
    fireEvent.change(getPasswordInput()!, { target: { value: 'errpass' } });
    fireEvent.click(getSubmitButton());

    await waitFor(() => {
      const body = document.body.textContent?.toLowerCase() ?? '';
      const hasError = body.includes('error') || body.includes('failed') || body.includes('server');
      expect(hasError).toBe(true);
    });
  });

  // --- Loading state ---

  it('disables submit button while register request is in flight', async () => {
    vi.mocked(registerApi).mockImplementationOnce(
      () =>
        new Promise((resolve) =>
          setTimeout(() => resolve({ id: 'u', email: 'e@e.com', display_name: 'E' }), 200)
        )
    );

    renderRegisterPage();
    fireEvent.change(getEmailInput()!, { target: { value: 'e@e.com' } });
    fireEvent.change(getPasswordInput()!, { target: { value: 'pass' } });

    const btn = getSubmitButton() as HTMLButtonElement;
    fireEvent.click(btn);

    expect(btn.disabled).toBe(true);
  });
});

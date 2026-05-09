/**
 * AppHeader.test.tsx — Round 15 / PR #23
 *
 * Verifies the AppHeader profile/settings shortcut now points at /settings
 * (per spec § 4.2 item 37). The /profile route remains wired in App.tsx for
 * existing bookmarks — that's tested separately.
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../store/authStore', () => {
  const state = { accessToken: 'test-token', user: { id: 'u1', email: 'a@b.c', display_name: 'Aly' } };
  const store = Object.assign(
    (selector: (s: typeof state) => unknown) => selector(state),
    { getState: () => state, subscribe: () => () => {}, setState: () => {} },
  );
  return { useAuthStore: store };
});

describe('AppHeader (Round 15 / PR #23)', () => {
  it('profile icon links to /settings', async () => {
    const { AppHeader } = await import('../components/AppHeader');
    const { container } = render(
      <MemoryRouter>
        <AppHeader />
      </MemoryRouter>,
    );

    const links = Array.from(container.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(links).toContain('/settings');
    expect(links).not.toContain('/profile');
  });
});

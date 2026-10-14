import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('../services/config.ts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/config.ts')>();
  return { ...actual, APP_CONFIG: { ...actual.APP_CONFIG, demoMode: false } };
});

import { LoginPage } from './LoginPage';
import { ProtectedRoute } from '../components/ProtectedRoute';
import { AuthProvider } from '../store/AuthContext';

function renderWithAuth(initialEntry: string) {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/dashboard" element={<div>Dashboard mock</div>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/protected" element={<div>Protected mock</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

beforeEach(() => {
  sessionStorage.clear();
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      access_token: 'test-access-token',
      expires_in: 900,
      role: 'nurse',
      username: 'nurse',
      full_name: 'Test Nurse',
    }),
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('authenticated login', () => {
  it('submits credentials to the API and opens the dashboard', async () => {
    renderWithAuth('/login');

    expect(screen.queryByText(/Demo Role Quick-Fill/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: 'nurse' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'NursePass123!' } });
    fireEvent.click(screen.getByRole('button', { name: /Sign in/i }));

    expect(await screen.findByText('Dashboard mock')).toBeInTheDocument();
    expect(JSON.parse(sessionStorage.getItem('vitalguard.operator.session') || '{}')).toMatchObject({
      role: 'nurse',
      username: 'nurse',
      token: 'test-access-token',
    });
  });

  it('shows an authentication error for rejected credentials', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({}),
    }));

    renderWithAuth('/login');
    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: 'someone-else' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'wrong-password' } });
    fireEvent.click(screen.getByRole('button', { name: /Sign in/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/Invalid username or password/i);
    expect(screen.queryByText('Dashboard mock')).not.toBeInTheDocument();
  });

  it('redirects to login when no authenticated session exists', () => {
    renderWithAuth('/protected');

    expect(screen.getByRole('heading', { name: /Clinical Portal Login/i })).toBeInTheDocument();
    expect(screen.queryByText('Protected mock')).not.toBeInTheDocument();
  });
});

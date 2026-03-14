/**
 * SURVEYOR — Auth context for managing authentication state.
 *
 * When AUTH_ENABLED is false on the backend, everything passes through
 * without requiring login.
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { auth, setAuthToken, clearAuthToken } from "../lib/api";

interface AuthState {
  loading: boolean;
  authEnabled: boolean;
  authenticated: boolean;
  username: string | null;
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    loading: true,
    authEnabled: false,
    authenticated: false,
    username: null,
  });

  // Check auth status on mount
  useEffect(() => {
    auth
      .status()
      .then((res) => {
        setState({
          loading: false,
          authEnabled: res.auth_enabled,
          authenticated: res.authenticated,
          username: res.username,
        });
      })
      .catch(() => {
        // If we can't reach the auth endpoint, assume auth is disabled
        setState({
          loading: false,
          authEnabled: false,
          authenticated: true,
          username: null,
        });
      });
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await auth.login(username, password);
    setAuthToken(res.token);
    setState((prev) => ({
      ...prev,
      authenticated: true,
      username: res.username,
    }));
  }, []);

  const logout = useCallback(() => {
    clearAuthToken();
    setState((prev) => ({
      ...prev,
      authenticated: false,
      username: null,
    }));
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

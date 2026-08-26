"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import {
  loginRequest,
  registerRequest,
  fetchMeRequest,
  type User,
} from "@/lib/auth-api";
import { ApiRequestError, friendlyError } from "@/lib/api";

interface AuthState {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  sessionError: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  retryValidation: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("trackflow_token");
}

function storeToken(token: string) {
  localStorage.setItem("trackflow_token", token);
}

function clearToken() {
  localStorage.removeItem("trackflow_token");
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const router = useRouter();

  useEffect(() => {
    const stored = getStoredToken();
    if (!stored) {
      const id = setTimeout(() => setIsLoading(false));
      return () => clearTimeout(id);
    }

    let cancelled = false;
    fetchMeRequest(stored)
      .then((me) => {
        if (cancelled) return;
        setToken(stored);
        setUser({
          id: me.profile.user_id,
          email: me.email,
          is_active: true,
          role: me.role,
          created_at: "",
        });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiRequestError && err.status === 401) {
          clearToken();
        } else {
          setSessionError(friendlyError(err));
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [retryNonce]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await loginRequest(email, password);
      storeToken(res.access_token);
      setToken(res.access_token);
      setUser(res.user);
    },
    [],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      await registerRequest(email, password);
      const res = await loginRequest(email, password);
      storeToken(res.access_token);
      setToken(res.access_token);
      setUser(res.user);
    },
    [],
  );

  const logout = useCallback(() => {
    clearToken();
    setToken(null);
    setUser(null);
    setSessionError(null);
    router.push("/login");
  }, [router]);

  const retryValidation = useCallback(() => {
    setSessionError(null);
    setIsLoading(true);
    setRetryNonce((n) => n + 1);
  }, []);

  const isAuthenticated = user !== null && token !== null;

  return (
    <AuthContext.Provider value={{ user, token, isLoading, isAuthenticated, sessionError, login, register, logout, retryValidation }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

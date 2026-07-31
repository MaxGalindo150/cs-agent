"use client";

// Client-side "who's logged in" state for the host-app simulation. Not a real
// auth system — it's a stand-in for whatever the host app's own login would
// hand off to the embedded support widget. Persisted to localStorage so a
// reload keeps you logged in as the same demo user.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { fetchDemoUsers } from "@/lib/identity/api";
import type { DemoUser } from "@/lib/identity/types";

const STORAGE_KEY = "csa:identity";

interface IdentityContextValue {
  /** All demo users the host app "knows about" (from the mock BNPL backend). */
  users: DemoUser[];
  /** The currently logged-in demo user, or null for an anonymous visitor. */
  activeUser: DemoUser | null;
  login: (user: DemoUser) => void;
  logout: () => void;
}

const IdentityContext = createContext<IdentityContextValue | null>(null);

export function IdentityProvider({ children }: { children: ReactNode }) {
  const [users, setUsers] = useState<DemoUser[]>([]);
  const [activeUser, setActiveUser] = useState<DemoUser | null>(null);

  useEffect(() => {
    fetchDemoUsers()
      .then((fetched) => {
        setUsers(fetched);
        const storedId = window.localStorage.getItem(STORAGE_KEY);
        const restored = fetched.find((u) => u.id === storedId) ?? null;
        setActiveUser(restored);
      })
      .catch(() => {
        // Mock-server unreachable: stay anonymous rather than block the page.
      });
  }, []);

  const login = useCallback((user: DemoUser) => {
    setActiveUser(user);
    window.localStorage.setItem(STORAGE_KEY, user.id);
  }, []);

  const logout = useCallback(() => {
    setActiveUser(null);
    window.localStorage.removeItem(STORAGE_KEY);
  }, []);

  return (
    <IdentityContext.Provider value={{ users, activeUser, login, logout }}>
      {children}
    </IdentityContext.Provider>
  );
}

export function useIdentity(): IdentityContextValue {
  const ctx = useContext(IdentityContext);
  if (!ctx) {
    throw new Error("useIdentity must be used within an IdentityProvider");
  }
  return ctx;
}

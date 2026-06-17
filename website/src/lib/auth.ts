import { api } from './api';

let currentUser: { id: number; email: string; name: string | null; is_admin: boolean } | null = null;
let listeners: Array<() => void> = [];

export function onAuthChange(fn: () => void) {
  listeners.push(fn);
  return () => { listeners = listeners.filter(l => l !== fn); };
}

function notify() {
  listeners.forEach(fn => fn());
}

export async function initAuth() {
  const token = localStorage.getItem('auth_token');
  if (token) {
    try {
      currentUser = await api.auth.me();
    } catch {
      localStorage.removeItem('auth_token');
      currentUser = null;
    }
  }
  notify();
}

export function getUser() {
  return currentUser;
}

export function isAuthenticated() {
  return currentUser !== null;
}

export function isAdmin() {
  return currentUser?.is_admin === true;
}

export async function login(email: string, password: string) {
  const result = await api.auth.login(email, password);
  localStorage.setItem('auth_token', result.access_token);
  currentUser = await api.auth.me();
  notify();
}

export async function register(email: string, password: string, name?: string) {
  const result = await api.auth.register(email, password, name);
  localStorage.setItem('auth_token', result.access_token);
  currentUser = await api.auth.me();
  notify();
}

export function logout() {
  localStorage.removeItem('auth_token');
  currentUser = null;
  notify();
}

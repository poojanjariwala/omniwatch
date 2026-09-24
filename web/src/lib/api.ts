/** Thin API client. Tokens live in memory + sessionStorage; the server is
 *  always the authority (routes re-verify JWT + RBAC server-side). */

export interface UserInfo {
  id: number;
  email: string;
  full_name: string;
  role: string;
  state_code?: string | null;
  org_id?: number | null;
}

const ACCESS_KEY = "ow_access_token";
const REFRESH_KEY = "ow_refresh_token";
const USER_KEY = "ow_user";

let actionToken: string | null = null;

export function setSession(tokens: { access_token: string; refresh_token: string },
                           user: UserInfo): void {
  sessionStorage.setItem(ACCESS_KEY, tokens.access_token);
  sessionStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_KEY);
}

export function getStoredUser(): UserInfo | null {
  const raw = sessionStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserInfo;
  } catch {
    return null;
  }
}

export function clearSession(): void {
  sessionStorage.removeItem(ACCESS_KEY);
  sessionStorage.removeItem(REFRESH_KEY);
  sessionStorage.removeItem(USER_KEY);
  actionToken = null;
}

export function setActionToken(token: string): void {
  actionToken = token;
}

import { apiBase } from "./config";

export async function login(email: string, password: string): Promise<UserInfo> {
  const body = await request("/api/auth/login", {
    method: "POST", json: { email, password },
    skipAuth: true,
  });
  const tokens = { access_token: body.access_token, refresh_token: body.refresh_token };
  setSession(tokens, body.user as UserInfo);
  return body.user as UserInfo;
}

export async function reauthenticate(password: string): Promise<string> {
  const body = await request("/api/auth/confirm-password", {
    method: "POST", json: { password },
  });
  setActionToken(body.action_token as string);
  return body.action_token as string;
}

export async function logoutRemote(): Promise<void> {
  try {
    await request("/api/auth/logout", {
      method: "POST",
      json: { refresh_token: getRefreshToken() ?? "" },
    });
  } catch {
    /* logout is best-effort */
  }
  clearSession();
}

interface ReqOpts {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  json?: unknown;
  form?: FormData;
  query?: Record<string, string | number | undefined>;
  skipAuth?: boolean;
  sensitive?: boolean; // include the re-auth action token header
}

async function raw(path: string, opts: ReqOpts, retry: boolean): Promise<Response> {
  const headers = new Headers();
  const token = getAccessToken();
  if (!opts.skipAuth && token) headers.set("Authorization", `Bearer ${token}`);
  if (opts.sensitive && actionToken) headers.set("X-Action-Token", actionToken);
  if (opts.json !== undefined) headers.set("Content-Type", "application/json");

  let url = apiBase() + path;
  if (opts.query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined && v !== "") qs.set(k, String(v));
    }
    const s = qs.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }

  const init: RequestInit = { method: opts.method ?? "GET", headers };
  if (opts.json !== undefined) init.body = JSON.stringify(opts.json);
  if (opts.form !== undefined) init.body = opts.form;

  const resp = await fetch(url, init);
  if (resp.status === 401 && !opts.skipAuth && retry) {
    const refreshed = await tryRefresh();
    if (refreshed) return raw(path, opts, false);
  }
  return resp;
}

export async function request<T = any>(path: string, opts: ReqOpts = {}): Promise<T> {
  const resp = await raw(path, opts, true);
  if (!resp.ok) {
    let detail = `${resp.status}`;
    try {
      const body = await resp.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export async function requestBlob(path: string, opts: ReqOpts = {}): Promise<Blob> {
  const resp = await raw(path, opts, true);
  if (!resp.ok) throw new ApiError(resp.status, "Download failed");
  return resp.blob();
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Single-flight refresh: parallel 401s must share one rotation, because
// local-mode refresh tokens are single-use (the second caller would present
// the just-revoked token and clear everyone's session).
let refreshInFlight: Promise<boolean> | null = null;

function tryRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

async function doRefresh(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) {
    clearSession();
    return false;
  }
  try {
    const resp = await fetch(apiBase() + "/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!resp.ok) {
      clearSession();
      return false;
    }
    const body = await resp.json();
    const user = getStoredUser();
    if (user) {
      setSession({ access_token: body.access_token, refresh_token: body.refresh_token }, user);
    } else {
      sessionStorage.setItem(ACCESS_KEY, body.access_token);
      sessionStorage.setItem(REFRESH_KEY, body.refresh_token);
    }
    return true;
  } catch {
    return false;
  }
}

export function apiErrorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

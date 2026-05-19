import type { ConnSettings } from "./types";

const STORAGE_KEY = "jcq_admin_conn";

export function loadSettings(): ConnSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...defaultSettings(), ...JSON.parse(raw) };
  } catch {}
  return defaultSettings();
}

export function saveSettings(s: ConnSettings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
}

function defaultSettings(): ConnSettings {
  return {
    baseUrl: "http://localhost:8001",
    baseToken: "",
    judgeUrl: "http://localhost:8002",
    judgeToken: "",
  };
}

async function apiFetch(
  url: string,
  token: string,
  init: RequestInit = {}
): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...((init.headers as Record<string, string>) ?? {}),
  };
  return fetch(url, { ...init, headers });
}

export function adminFetch(
  path: string,
  settings: ConnSettings,
  init: RequestInit = {}
) {
  if (!settings.baseUrl) throw new Error("authoring URL 설정이 비어있음");
  return apiFetch(settings.baseUrl + path, settings.baseToken, init);
}

export function judgeFetch(
  path: string,
  settings: ConnSettings,
  init: RequestInit = {}
) {
  if (!settings.judgeUrl) throw new Error("judge URL 설정이 비어있음");
  return apiFetch(settings.judgeUrl + path, settings.judgeToken, init);
}

export function backendFetch(
  path: string,
  settings: ConnSettings,
  init: RequestInit = {}
) {
  // notices는 backend(:8000)에 있음 — judgeUrl을 backend로 사용하거나 별도 baseUrl 사용
  // 현재 구조상 notices는 baseUrl(authoring)을 통해 프록시되거나 직접 호출
  // 기존 코드 기준 adminFetch로 호출했으므로 동일하게 유지
  return adminFetch(path, settings, init);
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function fmtDate(iso?: string): string {
  if (!iso) return "—";
  return iso.replace("T", " ").slice(0, 19);
}

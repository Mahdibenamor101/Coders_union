export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const KEY_STORAGE = "surveillance_api_key";

export function getApiKey(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(KEY_STORAGE) ?? "";
}

export function setApiKey(key: string) {
  localStorage.setItem(KEY_STORAGE, key);
}

export function clearApiKey() {
  localStorage.removeItem(KEY_STORAGE);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": getApiKey(),
      ...(options.headers || {}),
    },
  });
  if (response.status === 401 && typeof window !== "undefined") {
    window.location.href = "/login";
    throw new ApiError(401, "Non autorisé");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export function alertsWsUrl(): string {
  const base = API_URL.replace(/^http/, "ws");
  return `${base}/ws/alerts?api_key=${encodeURIComponent(getApiKey())}`;
}

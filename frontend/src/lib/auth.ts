import { api } from "./api";

export interface Me {
  id: string;
  email: string;
  name: string;
  role: "admin" | "manager" | "viewer";
  tenant: { id: string; name: string; plan: string; retention_days: number };
}

export function fetchMe(): Promise<Me> {
  return api<Me>("/auth/me");
}

export function canManage(me: Me | null): boolean {
  return me?.role === "admin" || me?.role === "manager";
}

export function isAdmin(me: Me | null): boolean {
  return me?.role === "admin";
}

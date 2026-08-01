export type ZoneType = "rayon" | "caisse" | "entree" | "sortie" | "reserve" | "autre";

export interface Zone {
  id?: string;
  name: string;
  type: ZoneType;
  polygon: [number, number][];
}

export interface Tenant {
  id: string;
  name: string;
  plan: string;
  retention_days: number;
  created_at: string;
}

export interface Store {
  id: string;
  tenant_id: string;
  name: string;
  address: string;
  timezone: string;
  created_at: string;
}

export interface Camera {
  id: string;
  store_id: string;
  name: string;
  status: string;
  last_seen_at: string | null;
  zones: Zone[];
  created_at: string;
}

export type AlertStatus = "pending" | "confirmed" | "false_positive" | "dismissed";

export interface Alert {
  id: string;
  camera_id: string;
  rule: string;
  severity: string;
  score: number;
  status: AlertStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  event_ts: string;
  clip_object_key: string | null;
  thumbnail_object_key: string | null;
  evidence: Record<string, unknown>[];
  created_at: string;
}

export interface CameraSettings {
  alert_threshold?: number;
  cooldown_seconds?: number;
  window_seconds?: number;
  dwell_seconds?: number;
  low_motion_radius?: number;
  min_shelf_seconds?: number;
  checkout_min_seconds?: number;
}

export interface RuleStats {
  rule: string;
  total: number;
  pending: number;
  confirmed: number;
  false_positive: number;
  dismissed: number;
  false_positive_rate: number | null;
}

export interface DayCount {
  date: string;
  count: number;
}

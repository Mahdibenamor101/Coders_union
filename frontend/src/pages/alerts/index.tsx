import Link from "next/link";
import { useEffect, useState } from "react";

import AlertThumbnail from "@/components/AlertThumbnail";
import { SeverityBadge, StatusBadge } from "@/components/Badges";
import Layout from "@/components/Layout";
import { api } from "@/lib/api";
import { RULE_LABELS, STATUS_LABELS, formatDate, ruleLabel } from "@/lib/labels";
import { Alert, Camera } from "@/lib/types";

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [status, setStatus] = useState("");
  const [rule, setRule] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<Camera[]>("/cameras").then(setCameras).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ limit: "100" });
    if (status) params.set("status", status);
    if (rule) params.set("rule", rule);
    api<Alert[]>(`/alerts?${params}`)
      .then(setAlerts)
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false));
  }, [status, rule]);

  const cameraName = (id: string) =>
    cameras.find((camera) => camera.id === id)?.name ?? id.slice(0, 8);

  return (
    <Layout>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-900">Incidents</h1>
        <div className="flex gap-2">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            <option value="">Tous les statuts</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <select
            value={rule}
            onChange={(e) => setRule(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            <option value="">Toutes les règles</option>
            {Object.entries(RULE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-slate-400">Chargement…</p>
      ) : alerts.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-400">
          Aucun incident pour ces filtres.
        </p>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert) => (
            <Link
              key={alert.id}
              href={`/alerts/${alert.id}`}
              className="flex items-center gap-4 rounded-lg border border-slate-200 bg-white px-4 py-3 hover:border-slate-400"
            >
              <AlertThumbnail alertId={alert.id} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-slate-900">
                    {ruleLabel(alert.rule)}
                  </span>
                  <SeverityBadge severity={alert.severity} />
                  <StatusBadge status={alert.status} />
                </div>
                <p className="mt-0.5 truncate text-sm text-slate-500">
                  {cameraName(alert.camera_id)} · score {alert.score} ·{" "}
                  {formatDate(alert.event_ts)}
                  {alert.reviewed_by ? ` · revu par ${alert.reviewed_by}` : ""}
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </Layout>
  );
}

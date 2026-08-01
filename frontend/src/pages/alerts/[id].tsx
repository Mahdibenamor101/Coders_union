import { useRouter } from "next/router";
import { useCallback, useEffect, useState } from "react";

import { SeverityBadge, StatusBadge } from "@/components/Badges";
import Layout from "@/components/Layout";
import { api } from "@/lib/api";
import { formatDate, ruleLabel } from "@/lib/labels";
import { Alert, AlertStatus } from "@/lib/types";

const REVIEW_ACTIONS: { status: AlertStatus; label: string; style: string }[] = [
  {
    status: "confirmed",
    label: "Confirmer",
    style: "bg-red-600 text-white hover:bg-red-500",
  },
  {
    status: "false_positive",
    label: "Faux positif",
    style: "bg-emerald-600 text-white hover:bg-emerald-500",
  },
  {
    status: "dismissed",
    label: "Ignorer",
    style: "bg-slate-200 text-slate-700 hover:bg-slate-300",
  },
];

export default function AlertDetailPage() {
  const router = useRouter();
  const alertId = typeof router.query.id === "string" ? router.query.id : null;

  const [alert, setAlert] = useState<Alert | null>(null);
  const [clipUrl, setClipUrl] = useState<string | null>(null);
  const [clipError, setClipError] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    if (!alertId) return;
    api<Alert>(`/alerts/${alertId}`).then(setAlert).catch(() => {});
    api<{ url: string }>(`/alerts/${alertId}/clip-url`)
      .then((data) => setClipUrl(data.url))
      .catch(() => setClipError(true));
  }, [alertId]);

  useEffect(load, [load]);

  async function review(status: AlertStatus) {
    if (!alertId) return;
    setSaving(true);
    try {
      const updated = await api<Alert>(`/alerts/${alertId}/review`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      setAlert(updated);
    } finally {
      setSaving(false);
    }
  }

  if (!alert) {
    return (
      <Layout>
        <p className="text-sm text-slate-400">Chargement…</p>
      </Layout>
    );
  }

  return (
    <Layout>
      <button
        onClick={() => router.back()}
        className="mb-3 text-sm text-slate-500 hover:text-slate-900"
      >
        ← Retour
      </button>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold text-slate-900">
              {ruleLabel(alert.rule)}
            </h1>
            <SeverityBadge severity={alert.severity} />
            <StatusBadge status={alert.status} />
          </div>
          <p className="mt-1 text-sm text-slate-500">
            Score {alert.score} · événement du {formatDate(alert.event_ts)}
          </p>

          <div className="mt-4 overflow-hidden rounded-lg border border-slate-200 bg-black">
            {clipUrl ? (
              <video controls src={clipUrl} className="aspect-video w-full" />
            ) : (
              <div className="flex aspect-video items-center justify-center text-sm text-slate-400">
                {clipError
                  ? "Clip indisponible pour cette alerte."
                  : "Chargement du clip…"}
              </div>
            )}
          </div>

          <h2 className="mb-2 mt-6 text-sm font-medium uppercase tracking-wide text-slate-500">
            Indices ayant déclenché l&apos;alerte
          </h2>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-500">
                  <th className="px-3 py-2 font-medium">Étape</th>
                  <th className="px-3 py-2 font-medium">Règle</th>
                  <th className="px-3 py-2 font-medium">Score</th>
                  <th className="px-3 py-2 font-medium">Détails</th>
                </tr>
              </thead>
              <tbody>
                {alert.evidence.map((finding, index) => (
                  <tr key={index} className="border-b border-slate-100 last:border-0">
                    <td className="px-3 py-2">{String(finding.stage ?? "—")}</td>
                    <td className="px-3 py-2">
                      {ruleLabel(String(finding.rule ?? ""))}
                    </td>
                    <td className="px-3 py-2">{String(finding.score ?? "—")}</td>
                    <td className="px-3 py-2 text-slate-500">
                      {Object.entries(finding)
                        .filter(
                          ([key]) => !["stage", "rule", "score", "ts"].includes(key)
                        )
                        .map(([key, value]) => `${key}: ${value}`)
                        .join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500">
            Revue humaine
          </h2>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            {alert.status !== "pending" ? (
              <div className="text-sm text-slate-600">
                <p>
                  Décision : <StatusBadge status={alert.status} />
                </p>
                <p className="mt-1">
                  Par {alert.reviewed_by ?? "—"} le {formatDate(alert.reviewed_at)}
                </p>
                <button
                  onClick={() => review("pending")}
                  disabled={saving}
                  className="mt-3 rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
                >
                  Remettre à vérifier
                </button>
              </div>
            ) : (
              <>
                <p className="text-sm text-slate-500">
                  La décision sera enregistrée à votre nom.
                </p>
                <div className="mt-3 flex flex-col gap-2">
                  {REVIEW_ACTIONS.map((action) => (
                    <button
                      key={action.status}
                      onClick={() => review(action.status)}
                      disabled={saving}
                      className={`rounded-md px-3 py-2 text-sm font-medium disabled:opacity-50 ${action.style}`}
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
                <p className="mt-3 text-xs text-slate-400">
                  La décision reste la vôtre : l&apos;alerte décrit un comportement
                  à vérifier, pas un fait établi.
                </p>
              </>
            )}
          </div>
        </section>
      </div>
    </Layout>
  );
}

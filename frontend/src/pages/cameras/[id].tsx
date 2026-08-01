/* eslint-disable @next/next/no-img-element */
import { useRouter } from "next/router";
import { MouseEvent, useCallback, useEffect, useState } from "react";

import { CameraStatusDot } from "@/components/Badges";
import Layout from "@/components/Layout";
import { api } from "@/lib/api";
import { ZONE_TYPE_COLORS, ZONE_TYPE_LABELS } from "@/lib/labels";
import { Camera, CameraSettings, Zone, ZoneType } from "@/lib/types";

const SETTINGS_FIELDS: { key: keyof CameraSettings; label: string; hint: string }[] = [
  { key: "alert_threshold", label: "Seuil d'alerte", hint: "défaut 60" },
  { key: "cooldown_seconds", label: "Cooldown (s)", hint: "défaut 60" },
  { key: "window_seconds", label: "Fenêtre des indices (s)", hint: "défaut 120" },
  { key: "dwell_seconds", label: "Seuil de présence (s)", hint: "défaut 30" },
  { key: "low_motion_radius", label: "Rayon faible mouvement", hint: "défaut 0.05" },
  { key: "min_shelf_seconds", label: "Temps min. en rayon (s)", hint: "défaut 10" },
  { key: "checkout_min_seconds", label: "Temps min. en caisse (s)", hint: "défaut 5" },
];

export default function CameraDetailPage() {
  const router = useRouter();
  const cameraId = typeof router.query.id === "string" ? router.query.id : null;

  const [camera, setCamera] = useState<Camera | null>(null);
  const [snapshotUrl, setSnapshotUrl] = useState<string | null>(null);
  const [zones, setZones] = useState<Zone[]>([]);
  const [draft, setDraft] = useState<[number, number][]>([]);
  const [zoneName, setZoneName] = useState("");
  const [zoneType, setZoneType] = useState<ZoneType>("rayon");
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!cameraId) return;
    api<Camera>(`/cameras/${cameraId}`)
      .then((data) => {
        setCamera(data);
        setZones(data.zones);
      })
      .catch(() => {});
    api<{ url: string }>(`/cameras/${cameraId}/snapshot-url`)
      .then((data) => setSnapshotUrl(data.url))
      .catch(() => setSnapshotUrl(null));
    api<CameraSettings>(`/cameras/${cameraId}/settings`)
      .then((data) =>
        setSettings(
          Object.fromEntries(
            Object.entries(data).map(([key, value]) => [key, String(value)])
          )
        )
      )
      .catch(() => {});
  }, [cameraId]);

  useEffect(load, [load]);

  function addPoint(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    setDraft((points) => [
      ...points,
      [Math.min(Math.max(x, 0), 1), Math.min(Math.max(y, 0), 1)],
    ]);
  }

  function finishZone() {
    if (draft.length < 3 || !zoneName) return;
    setZones((current) => [
      ...current,
      { name: zoneName, type: zoneType, polygon: draft },
    ]);
    setDraft([]);
    setZoneName("");
  }

  async function saveZones() {
    if (!cameraId) return;
    const saved = await api<Zone[]>(`/cameras/${cameraId}/zones`, {
      method: "PUT",
      body: JSON.stringify({ zones }),
    });
    setZones(saved);
    setMessage("Zones enregistrées — appliquées au worker en direct.");
  }

  async function saveSettings() {
    if (!cameraId) return;
    const payload: Record<string, number> = {};
    for (const [key, value] of Object.entries(settings)) {
      if (value.trim() !== "") payload[key] = Number(value);
    }
    await api(`/cameras/${cameraId}/settings`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    setMessage("Seuils enregistrés — appliqués au worker en direct.");
  }

  if (!camera) {
    return (
      <Layout>
        <p className="text-sm text-slate-400">Chargement…</p>
      </Layout>
    );
  }

  const toPoints = (polygon: [number, number][]) =>
    polygon.map(([x, y]) => `${x * 1000},${y * 1000}`).join(" ");

  return (
    <Layout>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{camera.name}</h1>
          <CameraStatusDot status={camera.status} />
        </div>
        <button
          onClick={load}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100"
        >
          Rafraîchir
        </button>
      </div>

      {message && (
        <p className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {message}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500">
            Zones — cliquer sur l&apos;image pour dessiner un polygone
          </h2>
          <div className="relative overflow-hidden rounded-lg border border-slate-200 bg-slate-900">
            {snapshotUrl ? (
              <img src={snapshotUrl} alt="Vue caméra" className="w-full" />
            ) : (
              <div className="flex aspect-video items-center justify-center text-sm text-slate-400">
                Pas encore d&apos;image (worker hors ligne ?) — le dessin reste possible.
              </div>
            )}
            <svg
              viewBox="0 0 1000 1000"
              preserveAspectRatio="none"
              className="absolute inset-0 h-full w-full cursor-crosshair"
              onClick={addPoint}
            >
              {zones.map((zone, index) => (
                <g key={zone.id ?? index}>
                  <polygon
                    points={toPoints(zone.polygon)}
                    fill={ZONE_TYPE_COLORS[zone.type]}
                    fillOpacity={0.25}
                    stroke={ZONE_TYPE_COLORS[zone.type]}
                    strokeWidth={3}
                    vectorEffect="non-scaling-stroke"
                  />
                  <text
                    x={zone.polygon[0][0] * 1000}
                    y={zone.polygon[0][1] * 1000 - 8}
                    fill={ZONE_TYPE_COLORS[zone.type]}
                    fontSize={28}
                  >
                    {zone.name}
                  </text>
                </g>
              ))}
              {draft.length > 0 && (
                <polygon
                  points={toPoints(draft)}
                  fill="#ffffff"
                  fillOpacity={0.2}
                  stroke="#ffffff"
                  strokeDasharray="6 4"
                  strokeWidth={2}
                  vectorEffect="non-scaling-stroke"
                />
              )}
              {draft.map(([x, y], index) => (
                <circle key={index} cx={x * 1000} cy={y * 1000} r={6} fill="#fff" />
              ))}
            </svg>
          </div>

          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="text-sm text-slate-700">
              Nom de la zone
              <input
                value={zoneName}
                onChange={(e) => setZoneName(e.target.value)}
                className="mt-1 block rounded-md border border-slate-300 px-3 py-2 text-sm"
                placeholder="ex. Rayon parfumerie"
              />
            </label>
            <label className="text-sm text-slate-700">
              Type
              <select
                value={zoneType}
                onChange={(e) => setZoneType(e.target.value as ZoneType)}
                className="mt-1 block rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                {Object.entries(ZONE_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={finishZone}
              disabled={draft.length < 3 || !zoneName}
              className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-40"
            >
              Terminer la zone ({draft.length} pts)
            </button>
            <button
              onClick={() => setDraft([])}
              disabled={draft.length === 0}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-100 disabled:opacity-40"
            >
              Annuler le tracé
            </button>
            <button
              onClick={saveZones}
              className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500"
            >
              Enregistrer les zones
            </button>
          </div>

          <ul className="mt-3 space-y-1">
            {zones.map((zone, index) => (
              <li
                key={zone.id ?? index}
                className="flex items-center justify-between rounded-md border border-slate-200 bg-white px-3 py-2 text-sm"
              >
                <span>
                  <span
                    className="mr-2 inline-block h-3 w-3 rounded-sm"
                    style={{ backgroundColor: ZONE_TYPE_COLORS[zone.type] }}
                  />
                  {zone.name}{" "}
                  <span className="text-slate-400">
                    ({ZONE_TYPE_LABELS[zone.type]}, {zone.polygon.length} pts)
                  </span>
                </span>
                <button
                  onClick={() =>
                    setZones((current) => current.filter((_, i) => i !== index))
                  }
                  className="text-red-500 hover:text-red-700"
                >
                  Supprimer
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500">
            Seuils du moteur de règles
          </h2>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            {SETTINGS_FIELDS.map((field) => (
              <label key={field.key} className="mb-2 block text-sm text-slate-700">
                {field.label}{" "}
                <span className="text-xs text-slate-400">({field.hint})</span>
                <input
                  type="number"
                  step="any"
                  value={settings[field.key] ?? ""}
                  onChange={(e) =>
                    setSettings((current) => ({
                      ...current,
                      [field.key]: e.target.value,
                    }))
                  }
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                  placeholder="défaut"
                />
              </label>
            ))}
            <button
              onClick={saveSettings}
              className="mt-2 w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700"
            >
              Enregistrer les seuils
            </button>
            <p className="mt-2 text-xs text-slate-400">
              Laisser vide pour revenir à la valeur par défaut. Le taux de faux
              positifs par règle (Statistiques) guide ces réglages.
            </p>
          </div>
        </section>
      </div>
    </Layout>
  );
}

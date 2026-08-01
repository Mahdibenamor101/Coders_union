import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { CameraStatusDot, SeverityBadge, StatusBadge } from "@/components/Badges";
import Layout from "@/components/Layout";
import { alertsWsUrl, api } from "@/lib/api";
import { formatDate, ruleLabel } from "@/lib/labels";
import { Alert, Camera } from "@/lib/types";

interface LiveEvent {
  alert_id: string;
  camera_id: string;
  rule: string;
  severity: string;
  score: number;
  received_at: string;
}

export default function LivePage() {
  const [connected, setConnected] = useState(false);
  const [liveEvents, setLiveEvents] = useState<LiveEvent[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const socketRef = useRef<WebSocket | null>(null);

  const refresh = useCallback(() => {
    api<Alert[]>("/alerts?status=pending&limit=10").then(setAlerts).catch(() => {});
    api<Camera[]>("/cameras").then(setCameras).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    let closed = false;

    function connect() {
      const socket = new WebSocket(alertsWsUrl());
      socketRef.current = socket;
      socket.onopen = () => setConnected(true);
      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "alert_created") {
            setLiveEvents((events) =>
              [
                { ...data, received_at: new Date().toISOString() },
                ...events,
              ].slice(0, 20)
            );
            refresh();
          }
        } catch {
          // message non JSON : ignoré
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!closed) setTimeout(connect, 3000);
      };
    }

    connect();
    return () => {
      closed = true;
      socketRef.current?.close();
    };
  }, [refresh]);

  const cameraName = (id: string) =>
    cameras.find((camera) => camera.id === id)?.name ?? id.slice(0, 8);

  return (
    <Layout>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Vue live</h1>
        <span className="inline-flex items-center gap-2 text-sm text-slate-500">
          <span
            className={`h-2 w-2 rounded-full ${
              connected ? "bg-emerald-500" : "bg-red-400"
            }`}
          />
          {connected ? "Temps réel connecté" : "Reconnexion…"}
        </span>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500">
            Comportements à vérifier
          </h2>
          <div className="space-y-2">
            {alerts.length === 0 && (
              <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
                Aucune alerte en attente de revue.
              </p>
            )}
            {alerts.map((alert) => (
              <Link
                key={alert.id}
                href={`/alerts/${alert.id}`}
                className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 hover:border-slate-400"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-slate-900">
                      {ruleLabel(alert.rule)}
                    </span>
                    <SeverityBadge severity={alert.severity} />
                    <StatusBadge status={alert.status} />
                  </div>
                  <p className="mt-0.5 text-sm text-slate-500">
                    {cameraName(alert.camera_id)} · score {alert.score} ·{" "}
                    {formatDate(alert.event_ts)}
                  </p>
                </div>
                <span className="text-sm text-slate-400">Vérifier →</span>
              </Link>
            ))}
          </div>

          <h2 className="mb-2 mt-6 text-sm font-medium uppercase tracking-wide text-slate-500">
            Flux temps réel
          </h2>
          <ul className="space-y-1 text-sm">
            {liveEvents.length === 0 && (
              <li className="text-slate-400">En attente d&apos;événements…</li>
            )}
            {liveEvents.map((event, index) => (
              <li key={`${event.alert_id}-${index}`} className="text-slate-600">
                <span className="text-slate-400">
                  {new Date(event.received_at).toLocaleTimeString("fr-FR")}
                </span>{" "}
                — {ruleLabel(event.rule)} ({cameraName(event.camera_id)}, score{" "}
                {event.score})
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500">
            Caméras
          </h2>
          <div className="space-y-2">
            {cameras.length === 0 && (
              <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-400">
                Aucune caméra.{" "}
                <Link href="/cameras" className="underline">
                  En ajouter une
                </Link>
                .
              </p>
            )}
            {cameras.map((camera) => (
              <Link
                key={camera.id}
                href={`/cameras/${camera.id}`}
                className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 hover:border-slate-400"
              >
                <span className="font-medium text-slate-900">{camera.name}</span>
                <CameraStatusDot status={camera.status} />
              </Link>
            ))}
          </div>
        </section>
      </div>
    </Layout>
  );
}

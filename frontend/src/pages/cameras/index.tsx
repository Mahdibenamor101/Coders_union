import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { CameraStatusDot } from "@/components/Badges";
import Layout from "@/components/Layout";
import { ApiError, api } from "@/lib/api";
import { Camera, Store } from "@/lib/types";

export default function CamerasPage() {
  const [stores, setStores] = useState<Store[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [storeName, setStoreName] = useState("");
  const [cameraName, setCameraName] = useState("");
  const [cameraStore, setCameraStore] = useState("");
  const [rtspUrl, setRtspUrl] = useState("");

  const refresh = useCallback(() => {
    api<Store[]>("/stores").then(setStores).catch(() => {});
    api<Camera[]>("/cameras").then(setCameras).catch(() => {});
  }, []);

  useEffect(refresh, [refresh]);

  async function createStore(event: FormEvent) {
    event.preventDefault();
    setError(null);
    await api("/stores", { method: "POST", body: JSON.stringify({ name: storeName }) });
    setStoreName("");
    refresh();
  }

  async function createCamera(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const camera = await api<Camera>("/cameras", {
        method: "POST",
        body: JSON.stringify({
          store_id: cameraStore,
          name: cameraName,
          rtsp_url: rtspUrl,
        }),
      });
      setCameraName("");
      setRtspUrl("");
      setMessage(
        `Caméra créée. Pour la suivre, renseignez WORKER_CAMERA_ID=${camera.id} dans .env puis redémarrez le worker.`
      );
      refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) {
        setError(
          "Limite de caméras du plan atteinte — passez à un plan supérieur (page Abonnement)."
        );
      } else if (e instanceof ApiError && e.status === 403) {
        setError("Votre rôle ne permet pas de créer une caméra.");
      } else {
        setError(e instanceof Error ? e.message : "Erreur");
      }
    }
  }

  const storeName_ = (id: string) =>
    stores.find((store) => store.id === id)?.name ?? "—";

  const inputClass =
    "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm";
  const buttonClass =
    "mt-3 rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700";

  return (
    <Layout>
      <h1 className="mb-4 text-xl font-semibold text-slate-900">Caméras</h1>

      {message && (
        <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {message}
        </p>
      )}
      {error && (
        <p className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}

      <div className="space-y-2">
        {cameras.length === 0 && (
          <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
            Aucune caméra enregistrée.
          </p>
        )}
        {cameras.map((camera) => (
          <Link
            key={camera.id}
            href={`/cameras/${camera.id}`}
            className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3 hover:border-slate-400"
          >
            <div>
              <span className="font-medium text-slate-900">{camera.name}</span>
              <p className="text-sm text-slate-500">
                {storeName_(camera.store_id)} · {camera.zones.length} zone(s)
              </p>
            </div>
            <CameraStatusDot status={camera.status} />
          </Link>
        ))}
      </div>

      <h2 className="mb-2 mt-8 text-sm font-medium uppercase tracking-wide text-slate-500">
        Configuration
      </h2>
      <div className="grid gap-4 md:grid-cols-2">
        <form
          onSubmit={createStore}
          className="rounded-lg border border-slate-200 bg-white p-4"
        >
          <h3 className="font-medium text-slate-900">1. Magasin</h3>
          <label className="mt-2 block text-sm text-slate-700">
            Nom du magasin
            <input
              value={storeName}
              onChange={(e) => setStoreName(e.target.value)}
              className={inputClass}
              required
            />
          </label>
          <button type="submit" className={buttonClass}>
            Créer le magasin
          </button>
          <p className="mt-2 text-xs text-slate-400">{stores.length} magasin(s)</p>
        </form>

        <form
          onSubmit={createCamera}
          className="rounded-lg border border-slate-200 bg-white p-4"
        >
          <h3 className="font-medium text-slate-900">2. Caméra</h3>
          <label className="mt-2 block text-sm text-slate-700">
            Magasin
            <select
              value={cameraStore}
              onChange={(e) => setCameraStore(e.target.value)}
              className={inputClass}
              required
            >
              <option value="">Choisir…</option>
              {stores.map((store) => (
                <option key={store.id} value={store.id}>
                  {store.name}
                </option>
              ))}
            </select>
          </label>
          <label className="mt-2 block text-sm text-slate-700">
            Nom
            <input
              value={cameraName}
              onChange={(e) => setCameraName(e.target.value)}
              className={inputClass}
              placeholder="ex. Entrée"
              required
            />
          </label>
          <label className="mt-2 block text-sm text-slate-700">
            URL RTSP
            <input
              value={rtspUrl}
              onChange={(e) => setRtspUrl(e.target.value)}
              className={inputClass}
              placeholder="rtsp://…"
              required
            />
          </label>
          <p className="mt-1 text-xs text-slate-400">
            Chiffrée en base, jamais réaffichée.
          </p>
          <button type="submit" className={buttonClass}>
            Créer la caméra
          </button>
        </form>
      </div>
    </Layout>
  );
}

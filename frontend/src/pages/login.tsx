import { useRouter } from "next/router";
import { FormEvent, useState } from "react";

import { API_URL, setApiKey } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/tenants`, {
        headers: { "X-API-Key": key },
      });
      if (!response.ok) {
        setError("Clé API invalide.");
        return;
      }
      setApiKey(key);
      router.push("/");
    } catch {
      setError(`API injoignable (${API_URL}).`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h1 className="text-lg font-semibold text-slate-900">Surveillance</h1>
        <p className="mt-1 text-sm text-slate-500">
          Connexion au dashboard (clé API — l&apos;authentification par comptes
          arrive en Phase 5).
        </p>
        <label className="mt-4 block text-sm font-medium text-slate-700">
          Clé API
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            placeholder="API_KEY du fichier .env"
            required
          />
        </label>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="mt-4 w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {loading ? "Connexion…" : "Se connecter"}
        </button>
      </form>
    </div>
  );
}

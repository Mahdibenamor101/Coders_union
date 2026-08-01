import { useRouter } from "next/router";
import { FormEvent, useState } from "react";

import { API_URL, setToken } from "@/lib/api";

export default function InvitationPage() {
  const router = useRouter();
  const token = typeof router.query.token === "string" ? router.query.token : "";
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/auth/invitations/accept`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, name, password }),
      });
      if (!response.ok) {
        setError("Invitation invalide, expirée ou déjà utilisée.");
        return;
      }
      const data = await response.json();
      setToken(data.access_token);
      router.push("/");
    } catch {
      setError(`API injoignable (${API_URL}).`);
    } finally {
      setLoading(false);
    }
  }

  const inputClass =
    "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm";

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      >
        <h1 className="text-lg font-semibold text-slate-900">
          Rejoindre l&apos;équipe
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Choisissez un mot de passe pour activer votre compte.
        </p>
        <label className="mt-4 block text-sm font-medium text-slate-700">
          Votre nom
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="mt-3 block text-sm font-medium text-slate-700">
          Mot de passe (8 caractères min)
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
            minLength={8}
            required
          />
        </label>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={loading || !token}
          className="mt-4 w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {loading ? "Activation…" : "Activer mon compte"}
        </button>
        {!token && (
          <p className="mt-2 text-sm text-amber-600">
            Lien d&apos;invitation incomplet (token manquant).
          </p>
        )}
      </form>
    </div>
  );
}

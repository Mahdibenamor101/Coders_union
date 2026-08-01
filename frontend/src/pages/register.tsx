import Link from "next/link";
import { useRouter } from "next/router";
import { FormEvent, useState } from "react";

import { API_URL, setToken } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [company, setCompany] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company_name: company,
          name,
          email,
          password,
        }),
      });
      if (response.status === 409) {
        setError("Cet email est déjà enregistré.");
        return;
      }
      if (!response.ok) {
        setError("Inscription impossible (mot de passe : 8 caractères min).");
        return;
      }
      const data = await response.json();
      setToken(data.access_token);
      router.push("/cameras");
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
          Créer votre organisation
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Plan de départ : <strong>starter</strong> (2 caméras, gratuit). Vous
          devenez administrateur et pourrez inviter votre équipe.
        </p>
        <label className="mt-4 block text-sm font-medium text-slate-700">
          Nom de l&apos;organisation
          <input
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            className={inputClass}
            placeholder="ex. Boutique Centre-Ville"
            required
          />
        </label>
        <label className="mt-3 block text-sm font-medium text-slate-700">
          Votre nom
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="mt-3 block text-sm font-medium text-slate-700">
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClass}
            required
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
          disabled={loading}
          className="mt-4 w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {loading ? "Création…" : "Créer et commencer"}
        </button>
        <p className="mt-4 text-center text-sm text-slate-500">
          Déjà un compte ?{" "}
          <Link href="/login" className="font-medium text-slate-900 underline">
            Se connecter
          </Link>
        </p>
      </form>
    </div>
  );
}

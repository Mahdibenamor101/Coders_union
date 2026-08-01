import { useEffect, useState } from "react";

import Layout from "@/components/Layout";
import { ApiError, api } from "@/lib/api";

interface TenantSettings {
  id: string;
  name: string;
  retention_days: number;
  multimodal_verification: boolean;
}

interface Billing {
  plan: string;
  subscription_status: string;
  camera_count: number;
  camera_limit: number;
  configured: boolean;
}

const PLANS = [
  { id: "starter", label: "Starter", cameras: 2, price: "Gratuit" },
  { id: "pro", label: "Pro", cameras: 10, price: "Abonnement mensuel" },
  { id: "business", label: "Business", cameras: 50, price: "Abonnement mensuel" },
];

export default function BillingPage() {
  const [billing, setBilling] = useState<Billing | null>(null);
  const [tenant, setTenant] = useState<TenantSettings | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api<Billing>("/billing").then(setBilling).catch(() => {});
    api<TenantSettings>("/tenant").then(setTenant).catch(() => {});
    if (
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("checkout") === "success"
    ) {
      setMessage(
        "Paiement confirmé — le plan sera mis à jour dès réception du webhook Stripe."
      );
    }
  }, []);

  async function upgrade(plan: string) {
    setMessage(null);
    try {
      const data = await api<{ url: string }>("/billing/checkout-session", {
        method: "POST",
        body: JSON.stringify({ plan }),
      });
      window.location.href = data.url;
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        setMessage(
          "La facturation n'est pas configurée (clés Stripe absentes du .env)."
        );
      } else {
        setMessage(e instanceof Error ? e.message : "Erreur");
      }
    }
  }

  return (
    <Layout>
      <h1 className="mb-4 text-xl font-semibold text-slate-900">Abonnement</h1>

      {message && (
        <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {message}
        </p>
      )}

      {billing && (
        <p className="mb-4 text-sm text-slate-600">
          Plan actuel : <strong>{billing.plan}</strong> ·{" "}
          {billing.camera_count}/{billing.camera_limit} caméras utilisées
          {billing.subscription_status !== "none" &&
            ` · abonnement ${billing.subscription_status}`}
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {PLANS.map((plan) => {
          const current = billing?.plan === plan.id;
          return (
            <div
              key={plan.id}
              className={`rounded-lg border bg-white p-4 ${
                current ? "border-slate-900" : "border-slate-200"
              }`}
            >
              <h2 className="font-semibold text-slate-900">{plan.label}</h2>
              <p className="mt-1 text-sm text-slate-500">
                Jusqu&apos;à {plan.cameras} caméras
              </p>
              <p className="mt-2 text-sm font-medium text-slate-700">{plan.price}</p>
              {current ? (
                <p className="mt-3 text-sm font-medium text-emerald-600">
                  Plan actuel
                </p>
              ) : plan.id !== "starter" ? (
                <button
                  onClick={() => upgrade(plan.id)}
                  className="mt-3 w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700"
                >
                  Passer à {plan.label}
                </button>
              ) : (
                <p className="mt-3 text-sm text-slate-400">
                  Plan de départ
                </p>
              )}
            </div>
          );
        })}
      </div>

      <p className="mt-6 text-xs text-slate-400">
        Le paiement passe par Stripe Checkout ; la mise à jour du plan est
        confirmée par webhook. En mode test, utilisez la carte 4242 4242 4242 4242.
      </p>

      {tenant && (
        <section className="mt-8 rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">
            Organisation
          </h2>
          <div className="mt-3 flex flex-wrap items-center gap-6 text-sm">
            <label className="flex items-center gap-2 text-slate-700">
              <input
                type="checkbox"
                checked={tenant.multimodal_verification}
                onChange={async (e) => {
                  const updated = await api<TenantSettings>("/tenant", {
                    method: "PATCH",
                    body: JSON.stringify({
                      multimodal_verification: e.target.checked,
                    }),
                  });
                  setTenant(updated);
                }}
              />
              Vérification des alertes par IA vision (réduction des faux positifs)
            </label>
            <label className="flex items-center gap-2 text-slate-700">
              Rétention des clips (jours, max 90)
              <input
                type="number"
                min={1}
                max={90}
                defaultValue={tenant.retention_days}
                onBlur={async (e) => {
                  const value = Number(e.target.value);
                  if (value >= 1 && value <= 90) {
                    const updated = await api<TenantSettings>("/tenant", {
                      method: "PATCH",
                      body: JSON.stringify({ retention_days: value }),
                    });
                    setTenant(updated);
                  }
                }}
                className="w-20 rounded-md border border-slate-300 px-2 py-1"
              />
            </label>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            La vérification vision n&apos;est appelée que sur les séquences déjà
            signalées ; elle ajuste le score, l&apos;alerte reste toujours soumise
            à revue humaine.
          </p>
        </section>
      )}
    </Layout>
  );
}

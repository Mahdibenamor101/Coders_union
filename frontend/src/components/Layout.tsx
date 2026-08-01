import Link from "next/link";
import { useRouter } from "next/router";
import { ReactNode, useEffect, useState } from "react";

import { clearApiKey, getApiKey } from "@/lib/api";

const NAV = [
  { href: "/", label: "Live" },
  { href: "/alerts", label: "Alertes" },
  { href: "/cameras", label: "Caméras" },
  { href: "/stats", label: "Statistiques" },
];

export default function Layout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getApiKey()) {
      router.replace("/login");
    } else {
      setReady(true);
    }
  }, [router]);

  if (!ready) return null;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-8">
            <span className="text-lg font-semibold text-slate-900">
              Surveillance
            </span>
            <nav className="flex gap-1">
              {NAV.map((item) => {
                const active =
                  item.href === "/"
                    ? router.pathname === "/"
                    : router.pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                      active
                        ? "bg-slate-900 text-white"
                        : "text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <button
            onClick={() => {
              clearApiKey();
              router.push("/login");
            }}
            className="text-sm text-slate-500 hover:text-slate-900"
          >
            Se déconnecter
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      <footer className="mx-auto max-w-6xl px-4 pb-6 text-xs text-slate-400">
        L&apos;IA signale, l&apos;humain décide : chaque alerte est un comportement à
        vérifier, jamais un verdict.
      </footer>
    </div>
  );
}

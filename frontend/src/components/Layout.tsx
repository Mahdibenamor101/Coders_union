import Link from "next/link";
import { useRouter } from "next/router";
import { ReactNode, useEffect, useState } from "react";

import { clearToken, getToken } from "@/lib/api";
import { Me, fetchMe, isAdmin } from "@/lib/auth";

const NAV = [
  { href: "/", label: "Live" },
  { href: "/alerts", label: "Alertes" },
  { href: "/cameras", label: "Caméras" },
  { href: "/stats", label: "Statistiques" },
];

const ADMIN_NAV = [
  { href: "/users", label: "Équipe" },
  { href: "/billing", label: "Abonnement" },
];

export default function Layout({
  children,
  me,
  onMe,
}: {
  children: ReactNode;
  me?: Me | null;
  onMe?: (me: Me) => void;
}) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [currentUser, setCurrentUser] = useState<Me | null>(me ?? null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
    fetchMe()
      .then((user) => {
        setCurrentUser(user);
        onMe?.(user);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  if (!ready) return null;

  const nav = isAdmin(currentUser) ? [...NAV, ...ADMIN_NAV] : NAV;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-8">
            <span className="text-lg font-semibold text-slate-900">
              {currentUser?.tenant.name ?? "Surveillance"}
            </span>
            <nav className="flex flex-wrap gap-1">
              {nav.map((item) => {
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
          <div className="flex items-center gap-3 text-sm text-slate-500">
            <span>{currentUser?.email}</span>
            <button
              onClick={() => {
                clearToken();
                router.push("/login");
              }}
              className="hover:text-slate-900"
            >
              Se déconnecter
            </button>
          </div>
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

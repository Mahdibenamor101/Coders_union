import { useEffect, useState } from "react";

import Layout from "@/components/Layout";
import { api } from "@/lib/api";
import { ruleLabel } from "@/lib/labels";
import { DayCount, RuleStats } from "@/lib/types";

export default function StatsPage() {
  const [days, setDays] = useState<DayCount[]>([]);
  const [rules, setRules] = useState<RuleStats[]>([]);

  useEffect(() => {
    api<DayCount[]>("/stats/alerts-per-day?days=14").then(setDays).catch(() => {});
    api<RuleStats[]>("/stats/rules").then(setRules).catch(() => {});
  }, []);

  const maxCount = Math.max(1, ...days.map((day) => day.count));

  return (
    <Layout>
      <h1 className="mb-4 text-xl font-semibold text-slate-900">Statistiques</h1>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          Alertes par jour (14 derniers jours)
        </h2>
        <div className="flex h-40 items-end gap-1">
          {days.map((day) => (
            <div
              key={day.date}
              className="group relative flex-1"
              title={`${day.date} : ${day.count} alerte(s)`}
            >
              <div
                className="w-full rounded-t bg-slate-800 transition-colors group-hover:bg-slate-600"
                style={{
                  height: `${(day.count / maxCount) * 100}%`,
                  minHeight: day.count > 0 ? "4px" : "1px",
                }}
              />
            </div>
          ))}
        </div>
        <div className="mt-1 flex justify-between text-xs text-slate-400">
          <span>{days[0]?.date ?? ""}</span>
          <span>{days[days.length - 1]?.date ?? ""}</span>
        </div>
      </section>

      <section className="mt-6 rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          Taux de faux positifs par règle
        </h2>
        <p className="mb-3 text-sm text-slate-500">
          C&apos;est l&apos;indicateur qui guide l&apos;ajustement des seuils par
          caméra : un taux élevé signifie que la règle se déclenche trop
          facilement.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="px-3 py-2 font-medium">Règle</th>
                <th className="px-3 py-2 font-medium">Total</th>
                <th className="px-3 py-2 font-medium">À vérifier</th>
                <th className="px-3 py-2 font-medium">Confirmées</th>
                <th className="px-3 py-2 font-medium">Faux positifs</th>
                <th className="px-3 py-2 font-medium">Ignorées</th>
                <th className="px-3 py-2 font-medium">Taux de FP</th>
              </tr>
            </thead>
            <tbody>
              {rules.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-slate-400">
                    Aucune alerte pour l&apos;instant.
                  </td>
                </tr>
              )}
              {rules.map((entry) => (
                <tr key={entry.rule} className="border-b border-slate-100 last:border-0">
                  <td className="px-3 py-2 font-medium text-slate-900">
                    {ruleLabel(entry.rule)}
                  </td>
                  <td className="px-3 py-2">{entry.total}</td>
                  <td className="px-3 py-2">{entry.pending}</td>
                  <td className="px-3 py-2">{entry.confirmed}</td>
                  <td className="px-3 py-2">{entry.false_positive}</td>
                  <td className="px-3 py-2">{entry.dismissed}</td>
                  <td className="px-3 py-2">
                    {entry.false_positive_rate === null ? (
                      <span className="text-slate-400">— (rien de revu)</span>
                    ) : (
                      <span
                        className={
                          entry.false_positive_rate > 0.5
                            ? "font-medium text-red-600"
                            : "font-medium text-slate-900"
                        }
                      >
                        {Math.round(entry.false_positive_rate * 100)} %
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </Layout>
  );
}

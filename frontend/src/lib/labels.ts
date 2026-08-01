// Vocabulaire produit (SPEC §1) : l'IA signale, l'humain décide.
// On parle toujours de « comportement à vérifier », jamais de « vol détecté ».

export const RULE_LABELS: Record<string, string> = {
  dissimulation: "Dissimulation possible",
  passage_sans_caisse: "Passage sans caisse",
  temps_anormal: "Temps anormal en zone",
  zone_interdite: "Zone interdite",
};

export const STATUS_LABELS: Record<string, string> = {
  pending: "À vérifier",
  confirmed: "Confirmée",
  false_positive: "Faux positif",
  dismissed: "Ignorée",
};

export const SEVERITY_LABELS: Record<string, string> = {
  high: "Haute",
  medium: "Moyenne",
  low: "Basse",
};

export const ZONE_TYPE_LABELS: Record<string, string> = {
  rayon: "Rayon",
  caisse: "Caisse",
  entree: "Entrée",
  sortie: "Sortie",
  reserve: "Réserve",
  autre: "Autre",
};

export const ZONE_TYPE_COLORS: Record<string, string> = {
  rayon: "#3b82f6",
  caisse: "#10b981",
  entree: "#8b5cf6",
  sortie: "#f59e0b",
  reserve: "#ef4444",
  autre: "#6b7280",
};

export function ruleLabel(rule: string): string {
  return RULE_LABELS[rule] ?? rule;
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "medium",
  });
}

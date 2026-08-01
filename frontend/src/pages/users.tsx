import { FormEvent, useCallback, useEffect, useState } from "react";

import Layout from "@/components/Layout";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/labels";

interface TeamUser {
  id: string;
  email: string;
  name: string;
  role: string;
  created_at: string;
}

interface PendingInvitation {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  accepted_at: string | null;
}

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrateur",
  manager: "Manager",
  viewer: "Lecture seule",
};

export default function UsersPage() {
  const [users, setUsers] = useState<TeamUser[]>([]);
  const [invitations, setInvitations] = useState<PendingInvitation[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("viewer");
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api<TeamUser[]>("/users").then(setUsers).catch(() => {});
    api<PendingInvitation[]>("/invitations").then(setInvitations).catch(() => {});
  }, []);

  useEffect(refresh, [refresh]);

  async function invite(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setInviteUrl(null);
    try {
      const data = await api<{ invite_url: string }>("/invitations", {
        method: "POST",
        body: JSON.stringify({ email, role }),
      });
      setInviteUrl(data.invite_url);
      setEmail("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    }
  }

  async function removeUser(id: string) {
    await api(`/users/${id}`, { method: "DELETE" });
    refresh();
  }

  return (
    <Layout>
      <h1 className="mb-4 text-xl font-semibold text-slate-900">Équipe</h1>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-500">
                  <th className="px-3 py-2 font-medium">Utilisateur</th>
                  <th className="px-3 py-2 font-medium">Rôle</th>
                  <th className="px-3 py-2 font-medium">Depuis</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-3 py-2">
                      <span className="font-medium text-slate-900">
                        {user.name || user.email}
                      </span>
                      {user.name && (
                        <span className="ml-2 text-slate-400">{user.email}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">{ROLE_LABELS[user.role] ?? user.role}</td>
                    <td className="px-3 py-2 text-slate-500">
                      {formatDate(user.created_at)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        onClick={() => removeUser(user.id)}
                        className="text-red-500 hover:text-red-700"
                      >
                        Retirer
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2 className="mb-2 mt-6 text-sm font-medium uppercase tracking-wide text-slate-500">
            Invitations en attente
          </h2>
          <ul className="space-y-1 text-sm">
            {invitations.filter((i) => !i.accepted_at).length === 0 && (
              <li className="text-slate-400">Aucune invitation en attente.</li>
            )}
            {invitations
              .filter((invitation) => !invitation.accepted_at)
              .map((invitation) => (
                <li
                  key={invitation.id}
                  className="rounded-md border border-slate-200 bg-white px-3 py-2"
                >
                  {invitation.email} — {ROLE_LABELS[invitation.role]} · expire le{" "}
                  {formatDate(invitation.expires_at)}
                </li>
              ))}
          </ul>
        </section>

        <section>
          <form
            onSubmit={invite}
            className="rounded-lg border border-slate-200 bg-white p-4"
          >
            <h2 className="font-medium text-slate-900">Inviter un membre</h2>
            <label className="mt-2 block text-sm text-slate-700">
              Email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                required
              />
            </label>
            <label className="mt-2 block text-sm text-slate-700">
              Rôle
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                <option value="viewer">Lecture seule</option>
                <option value="manager">Manager</option>
                <option value="admin">Administrateur</option>
              </select>
            </label>
            <button
              type="submit"
              className="mt-3 w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700"
            >
              Générer l&apos;invitation
            </button>
            {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
            {inviteUrl && (
              <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
                Lien d&apos;invitation (à transmettre — l&apos;envoi d&apos;email
                arrive avec le SMTP) :
                <code className="mt-1 block break-all">{inviteUrl}</code>
              </div>
            )}
          </form>
        </section>
      </div>
    </Layout>
  );
}

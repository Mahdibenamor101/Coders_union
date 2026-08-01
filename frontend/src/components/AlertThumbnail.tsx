/* eslint-disable @next/next/no-img-element */
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

export default function AlertThumbnail({ alertId }: { alertId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api<{ url: string }>(`/alerts/${alertId}/thumbnail-url`)
      .then((data) => !cancelled && setUrl(data.url))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [alertId]);

  if (failed || !url) {
    return (
      <div className="flex h-14 w-24 items-center justify-center rounded bg-slate-200 text-xs text-slate-400">
        {failed ? "Sans image" : "…"}
      </div>
    );
  }
  return (
    <img
      src={url}
      alt="Miniature de l'alerte"
      className="h-14 w-24 rounded object-cover"
      onError={() => setFailed(true)}
    />
  );
}

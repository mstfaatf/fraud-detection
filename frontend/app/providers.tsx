"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  // One QueryClient per browser session, created lazily via useState so it
  // survives re-renders without being recreated -- the standard pattern for
  // TanStack Query under Next.js App Router (a module-level client would be
  // shared across requests on the server, which is wrong for per-request
  // server rendering; this component is itself client-only, so that's moot
  // here, but the pattern is kept for when server-side prefetching is added).
  const [queryClient] = useState(() => new QueryClient());

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

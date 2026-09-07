/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enables Next's minimal-footprint "standalone" build output
  // (.next/standalone/, tracing only the node_modules actually required at
  // runtime, plus a self-contained server.js). Added specifically for
  // frontend/Dockerfile's runtime stage -- without it, a Docker runtime stage
  // would need the full node_modules tree (all devDependencies included) to
  // run `next start`, which is far larger than necessary. Harmless for the
  // existing Vercel deployment: Vercel has its own build/output pipeline and
  // does not consume .next/standalone/ at all, so this has no effect there.
  output: "standalone",

  // Lightweight security headers, same three added to the backend
  // (backend/app/main.py's _security_headers middleware) -- not a full CSP
  // (this app mounts a cross-origin Stripe Elements iframe on /checkout, and
  // a hand-tuned CSP that doesn't break that flow is real, non-trivial work
  // out of proportion for a portfolio demo with no user accounts/sessions to
  // protect; see SECURITY_AUDIT.md). Vercel already sends
  // Strict-Transport-Security by default, so that's not repeated here.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;

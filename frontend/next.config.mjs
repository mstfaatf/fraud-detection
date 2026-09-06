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
};

export default nextConfig;

# syntax=docker/dockerfile:1
#
# Production-style multi-stage Dockerfile for the Next.js frontend -- built
# for LOCAL full-stack Docker Compose use and containerization practice. This
# is NOT how the live public frontend is deployed: Vercel builds this app
# directly from its own Git-connected pipeline (see CLAUDE.md's Phase 8 part 1
# deploy notes) and never touches this file.
#
# Unlike backend/Dockerfile, this app has no imports outside its own
# directory (confirmed before writing this -- no `../../` imports anywhere
# under app/, components/, lib/), so the build context is just frontend/
# itself, not the repo root:
#
#   docker build -t fraud-frontend -f frontend/Dockerfile ./frontend \
#     --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000
#
# docker-compose.yml (Phase 11 part 2) should use `build: {context: ./frontend,
# dockerfile: Dockerfile}`.
#
# ---- NEXT_PUBLIC_* env vars: build-time, not runtime -- read this before
# touching either ARG below ----
# Next.js inlines every `NEXT_PUBLIC_*` env var directly into the client
# JavaScript bundle at `next build` time (via webpack's DefinePlugin) -- it is
# NOT read from `process.env` in the browser, or by the server, at request
# time. Concretely, that means:
#   - Setting NEXT_PUBLIC_API_URL under docker-compose.yml's `environment:`
#     block would have ZERO effect on an already-built image. The value baked
#     in at `docker build` time (via the ARG below) is permanent for that
#     image; the only way to change it is to rebuild.
#   - Inside a Compose network, the backend is NOT reachable at `localhost`
#     from the frontend container -- it must be the backend's Compose
#     *service name* (e.g. `http://backend:8000`), since containers on the
#     same Compose network resolve each other by service name.
#   - This is exactly the common Next.js/Docker footgun: shipping an image
#     with NEXT_PUBLIC_API_URL still baked in as `localhost` (correct for
#     `next dev` on a host machine, wrong inside a container) because it was
#     set as a runtime `environment:` var instead of a build-time
#     `--build-arg`.
# docker-compose.yml must therefore pass this as a `build.args` entry, not an
# `environment:` entry, pointed at the backend service's Compose name.

# ---- deps stage: install dependencies once, cached separately from source changes ----
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- build stage: compile the production Next.js build ----
FROM node:24-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time-only args -- see the NEXT_PUBLIC_* note above. Defaulted to the
# same localhost value frontend/.env.local.example uses, so a standalone
# `docker build` with no --build-arg still produces a runnable image (just
# one that expects the backend on the host's localhost, not a Compose
# network); Compose overrides these with the backend's real service-name URL.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=$NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY

RUN npm run build

# ---- runtime stage: only the standalone server output, no source or devDependencies ----
FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production

# `output: "standalone"` (next.config.mjs -- added specifically for this
# Dockerfile; this project's next.config.mjs had no `output` setting before)
# makes `next build` emit a self-contained server.js plus only the
# node_modules actually required at runtime, traced from the real dependency
# graph -- far smaller than copying the full node_modules tree (every
# devDependency included) into this stage the way a plain `next start`
# runtime would require.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# No frontend/public/ directory exists in this project as of this Dockerfile
# (confirmed before writing it) -- if one is ever added, also add:
#   COPY --from=builder /app/public ./public

RUN addgroup -S nodejs -g 1001 && adduser -S nextjs -u 1001 -G nodejs \
    && chown -R nextjs:nodejs /app
USER nextjs

# Configurable port (default matches this project's local-dev convention,
# `npm run dev` on 3000) and explicit 0.0.0.0 binding -- the standalone
# server.js Next generates reads both PORT and HOSTNAME from the environment.
ENV PORT=3000 \
    HOSTNAME=0.0.0.0
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "require('http').get('http://localhost:' + (process.env.PORT || 3000), r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["node", "server.js"]

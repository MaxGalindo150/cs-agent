# Dev image for the frontend (Next.js 16 + React 19, npm).
#
# Bakes in dependencies only; source is bind-mounted at runtime (see
# ../docker-compose.yml) so `next dev` hot-reloads on code changes without a
# rebuild. Rebuild only when package.json/package-lock.json change.
#
# NOTE: this is a dev image (Next dev server, Turbopack). A production image
# (multi-stage `next build` + standalone output, non-root) is out of scope here.
#
# Debian slim over alpine: Turbopack/SWC ship prebuilt native binaries against
# glibc, and musl variants have been the usual source of "module not found"
# surprises. Node 22 LTS — Next 16 requires >= 20.9.
FROM node:22-bookworm-slim

WORKDIR /app

# Copied first so the dependency layer is cached independently of the source.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

# In Next 16 `next dev` already defaults to hostname 0.0.0.0 and port 3000, so
# it accepts connections from outside the container with no extra flags.
CMD ["npm", "run", "dev"]

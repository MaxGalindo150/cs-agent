# Dev image for the BNPL mock server (Hono + Bun).
#
# Bakes in dependencies only; source is bind-mounted at runtime (see
# ../docker-compose.yml) so `bun --watch` picks up code changes without a
# rebuild. Rebuild only when package.json/bun.lock change.
FROM oven/bun:1

WORKDIR /app

COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .

EXPOSE 3001

CMD ["bun", "--watch", "src/server.ts"]

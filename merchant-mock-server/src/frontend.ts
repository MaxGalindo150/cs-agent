import { Hono } from "hono";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { basename, dirname, join } from "path";

const frontendRoutes = new Hono();

const PUBLIC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "public");

const ASSET_CONTENT_TYPES: Record<string, string> = {
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

// Serve the SPA at /dashboard
frontendRoutes.get("/dashboard", (c) => {
  const html = readFileSync(join(PUBLIC_DIR, "index.html"), "utf-8");
  return c.html(html);
});

// Static assets (Cashea logos). basename() strips any path segment, so a
// request for ../../etc/passwd can never escape public/assets.
frontendRoutes.get("/assets/:file", (c) => {
  const file = basename(c.req.param("file"));
  const extension = file.slice(file.lastIndexOf("."));
  const contentType = ASSET_CONTENT_TYPES[extension];
  if (!contentType) return c.text("Not found", 404);

  try {
    const body = readFileSync(join(PUBLIC_DIR, "assets", file));
    return c.body(body, 200, {
      "Content-Type": contentType,
      "Cache-Control": "public, max-age=3600",
    });
  } catch {
    return c.text("Not found", 404);
  }
});

export { frontendRoutes };

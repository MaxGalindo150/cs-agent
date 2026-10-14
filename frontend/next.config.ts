import type { NextConfig } from "next";

// Origins allowed to iframe /embed (the support widget), space-separated in
// CSP source syntax, e.g. "https://merchants.cashea.app". Unset means
// same-origin only — a host must be allowlisted explicitly, never by default.
const embedFrameAncestors = process.env.EMBED_FRAME_ANCESTORS?.trim() || "";

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/embed",
        headers: [
          {
            key: "Content-Security-Policy",
            value: `frame-ancestors 'self' ${embedFrameAncestors}`.trim(),
          },
        ],
      },
    ];
  },
};

export default nextConfig;

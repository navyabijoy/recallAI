import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin Turbopack's workspace root to this frontend directory. A stray
  // package-lock.json in the repo root made Turbopack infer the whole monorepo
  // as its root and try to watch/compile backend/venv + root node_modules,
  // which pegged all CPU cores and hung every compile. Absolute path required.
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;

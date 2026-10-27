import type { NextConfig } from "next";

// FantaBall is a client-rendered app that talks to the Flask API, so Cache Components /
// partial prefetching (enabled by the generator) are turned off to keep behaviour simple.
const nextConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;

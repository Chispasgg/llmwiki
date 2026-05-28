import type { NextConfig } from "next";
import path from "path";
import fs from "fs";
import { withSentryConfig } from "@sentry/nextjs";

const versionFile = path.join(__dirname, "..", "VERSION");
const appVersion = fs.existsSync(versionFile)
  ? fs.readFileSync(versionFile, "utf-8").trim()
  : "dev";

const nextConfig: NextConfig = {
  basePath: "/wiki",
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname),
  env: {
    NEXT_PUBLIC_APP_VERSION: appVersion,
  },
};

export default withSentryConfig(nextConfig, {
  silent: true,
  disableLogger: true,
});

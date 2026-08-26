// Learn more: https://docs.expo.dev/guides/customizing-metro/
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// --- zustand web fix -------------------------------------------------------
// zustand's package "exports" map points its "import" condition (which Metro
// selects for the web bundle) at ./esm/index.mjs — the only build that uses
// Vite-style `import.meta.env`. `import.meta` is a *parse-time* error inside
// Metro's classic-script web bundle ("Cannot use 'import.meta' outside a
// module"), which blanks the entire page.
//
// zustand's top-level "main" field (./index.js, CommonJS, uses process.env) is
// safe on every platform. Disable package-exports resolution for zustand ONLY
// so it falls back to "main"; all other packages keep normal exports support.
const originalResolveRequest = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName === 'zustand' || moduleName.startsWith('zustand/')) {
    return context.resolveRequest(
      { ...context, unstable_enablePackageExports: false },
      moduleName,
      platform,
    );
  }
  return (originalResolveRequest ?? context.resolveRequest)(
    context,
    moduleName,
    platform,
  );
};

module.exports = config;

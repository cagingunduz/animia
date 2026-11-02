// Bundles each style kit (src/<style>/entry.js) into kits/<style>.js: one classic script per style, setting a global.
//   cd render_service/studio && npm ci && npm run build
import { build } from 'esbuild';
const KITS = { whiteboard: 'WB', 'scifi-toon': 'TOON', 'paper-lantern': 'LB' };
for (const [style, global] of Object.entries(KITS)) {
  await build({
    entryPoints: [`src/${style}/entry.js`], bundle: true, format: 'iife', globalName: `__${global}`, target: 'es2020', minify: true,
    legalComments: 'none', loader: { '.json': 'json' }, outfile: `kits/${style}.js`,
    footer: { js: `window.${global} = __${global};` },
    banner: { js: `/* Animave Style Studio: ${style} kit. Engine adapted from github.com/lemomo-ai/lemo-opuscar (MIT, LICENSE_lemo-opuscar). Source: render_service/studio/src/${style}. */` },
  });
  console.log(`kits/${style}.js`);
}

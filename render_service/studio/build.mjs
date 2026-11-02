// Bundles each style kit (src/<style>/entry.js) into kits/<style>.js: one classic script per style, setting a global.
//   cd render_service/studio && npm ci && npm run build
import { build } from 'esbuild';
// style -> [global, output file]; kits that use three.js end in .three.js (the render service's lint looks for it)
const KITS = { whiteboard: ['WB', 'whiteboard.js'], 'scifi-toon': ['TOON', 'scifi-toon.js'], 'paper-lantern': ['LB', 'paper-lantern.js'], teardown: ['TD', 'teardown.three.js'], 'caption-news': ['CN', 'caption-news.js'], telestrator: ['TL', 'telestrator.js'], premium: ['PR', 'premium.js'], 'collage-doc': ['CD', 'collage-doc.js'] };
for (const [style, [global, file]] of Object.entries(KITS)) {
  await build({
    entryPoints: [`src/${style}/entry.js`], bundle: true, format: 'iife', globalName: `__${global}`, target: 'es2020', minify: true,
    legalComments: 'none', loader: { '.json': 'json' }, outfile: `kits/${file}`,
    footer: { js: `window.${global} = __${global};` },
    banner: { js: `/* Animave Style Studio: ${style} kit. Engine adapted from github.com/lemomo-ai/lemo-opuscar (MIT, LICENSE_lemo-opuscar)${file.includes('three') ? ', three.js (MIT, THREE_LICENSE)' : ''}. Source: render_service/studio/src/${style}. */` },
  });
  console.log(`kits/${file}`);
}

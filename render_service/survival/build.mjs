// Bundles src/entry.js (stage.js + three.js 0.160 + post passes + cannon-es) into stage.three.js, one classic script.
//   cd render_service/survival && npm ci && npm run build
import { build } from 'esbuild';
await build({
  entryPoints: ['src/entry.js'], bundle: true, format: 'iife', target: 'es2020', minify: true, legalComments: 'none',
  outfile: 'stage.three.js',
  banner: { js: '/* Animave survival kit: stage.js adapted from github.com/Theoxmotion/story-video-studio (MIT, LICENSE_story-video-studio), three.js (MIT, THREE_LICENSE), cannon-es (MIT, CANNON_LICENSE). Source: render_service/survival/src. */' },
});
console.log('stage.three.js built');

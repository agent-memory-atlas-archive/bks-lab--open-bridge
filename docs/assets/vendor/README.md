# Vendored libraries for the landing-page stage

Served from this folder so the site stays self-contained (no CDN, no network
request). Used only by `docs/assets/story.js` on `docs/index.html`.

| File | Version | Source | Licence |
|---|---|---|---|
| `three.module.min.js`, `three.core.js` | three.js 0.186.1 | https://cdn.jsdelivr.net/npm/three@0.186.1/build/ | MIT |

`three.module.min.js` imports `./three.core.js` by that name, so the core file
keeps the unminified-sounding name although it is the minified build.

The scroll mechanics are not a library: `docs/assets/scroll-engine.js` is our
own, MIT like the rest of the repo.

Fonts in `../fonts/` (Inter variable, Playfair Display 500, latin subset) come
from Fontsource and are licensed under the SIL Open Font License 1.1.

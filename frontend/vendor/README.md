# vendor/

## cheo-orb (temporary, POC only)

`vendor/cheo-orb/` is a copy of the **built** `@cashea/cheo` package (v0.1.0:
`dist/`, `package.json`, `README.md`, `LICENSE`) from the sibling `cheo-orb`
repo. `package.json` depends on it with `"@cashea/cheo": "file:./vendor/cheo-orb"`,
and `public/cheo-orb.js` is a copy of `dist/cheo-orb.js` for `public/widget.js`.

It exists only because the package is not published to npm yet.

### What to do at MVP

Replace this with a properly released npm package:

1. Publish `@cashea/cheo` to npm from its own Cashea repo (tag `vX.Y.Z`, the
   release workflow, `NPM_TOKEN`, the `@cashea` npm org).
2. In `package.json`, change `file:./vendor/cheo-orb` to a pinned semver range
   and run `npm install`.
3. Delete `vendor/`, and the `COPY vendor ./vendor` line in `Dockerfile`.
4. Stop committing `public/cheo-orb.js`: serve the script from the package
   (copy it from `node_modules/@cashea/cheo/dist/` in a build step) or pin it
   on a CDN, so the widget and the app never drift apart.

Until then, after any change to the orb, rebuild `../cheo-orb` and re-copy
`dist/` here and `dist/cheo-orb.js` to `public/`.

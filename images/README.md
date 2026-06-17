# Chat avatar images

Drop your two avatar images in **this folder**, named exactly:

| File        | Used for          | Fallback if missing |
|-------------|-------------------|---------------------|
| `bot.png`   | AI / assistant    | 🤖 emoji            |
| `user.png`  | Human / you       | `U` letter          |

## Specs
- **Format:** PNG (filenames are hardcoded as `.png` in `index.html`).
- **Size:** 128×128 px recommended. They're displayed at 32×32 in a rounded
  box (`object-fit: cover`), so square images look best.

## How it works
- This folder is mounted read-only into the nginx `web` container at
  `/usr/share/nginx/html/images` (see `../docker-compose.yml`).
- Files are served **live** — just add/replace them and refresh the browser.
  No container restart needed.
- If a file is missing or fails to load, the avatar falls back to the
  emoji/letter above, so nothing breaks.

## Want JPGs instead?
The references live in `../index.html` (search for `images/bot.png` /
`images/user.png`). Change the extensions there if you switch formats.

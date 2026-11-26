# ChromiumChanger 0.2 (Windows)

A desktop app that downloads **ungoogled-chromium** and customizes it for you: Google removal, custom name/icon,
ad blocking, profiles, developer options, and an optional AI assistant. No source patching: it works through
**policies (registry) + launch flags + a built-in extension + exe branding**.

## Run (from source)
1. Install Python 3.9+ (the Windows installer from python.org includes tkinter).
2. Double-click `run.bat` (or `run_debug.bat` to see a console with errors).
3. Home tab: 1. Install -> 2. Apply settings -> 3. Launch.

Start the browser from the app, from `Launch <name>.bat`, or from the desktop shortcut. Opening the browser .exe
directly skips the extensions and flags.

## Build an .exe / installer
- `build_exe.bat` -> `dist\ChromiumChanger\ChromiumChanger.exe` (+ `dist\ChromiumChanger-win64.zip`)
- `build_installer.bat` -> `dist\ChromiumChanger-Setup.exe` (needs Inno Setup 6; per-user install, no admin)
- The installed app stores its data in `%LOCALAPPDATA%\ChromiumChanger\workspace`.

## Features
- **Google removal, ad blocking (uBlock Origin Lite or other extension), theme, dark mode, search engine, site rules**
- **Profiles**: separate settings, mods, history and browser data. New / duplicate / rename / delete / switch.
- **Export / import**: `.ccprofile` file = settings + mods only (never browsing data or API keys). Imported mods that
  contain JavaScript are imported disabled until you review them.
- **Mods**: add your own CSS/JS content scripts without AI (Mods tab), or let the AI propose them.
- **AI (optional, off by default)**: local Ollama or an API (OpenAI-compatible incl. Grok/LM Studio, Anthropic).
  The AI only proposes a plan; you review and approve it. Dangerous flags are rejected and risky JS is flagged.
- **Developer tab**: auto-open DevTools, allow localhost certificates, browser log, DevTools experiments,
  minimal cache, one-click internal pages (chrome://inspect, extensions, policy, version...), folder shortcuts.
- **History**: a snapshot is saved before every change; restore any point.

## New tab page

Settings -> "New tab page" turns on a built-in start page for new tabs: a search box (it uses your default
search engine), a clock with the date, an optional greeting and up to 12 shortcut tiles (`Name | https://address`).
It lives in the built-in extension, runs fully offline and sends nothing anywhere. Colors follow your theme color
and dark mode setting. The AI can switch it on too ("new tab with a clock and a search bar"). Only one extension
can own the new tab page; incognito windows keep the browser's normal page.

## Certificate errors (VM / fresh Windows)

If downloads fail with `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate` (typical on a fresh virtual
machine whose Windows has not yet fetched its root certificates), the app retries once with the CA bundle shipped in
`assets/cacert.pem` (Mozilla root certificates taken from the Python `certifi` package, MPL-2.0). Certificate checking is
never turned off. If it still fails, check the date/time of the machine, security software or a proxy that intercepts HTTPS,
and run Windows Update.

## Administrator rights
Policy-based settings (default search engine, homepage, site block/allow lists, WebRTC/cookie/DNT) are written to the
registry, which Windows only allows for administrators. Use "Restart as administrator" in the app. Without admin,
those settings are skipped; everything else (flags, ad blocker, theme, mods) still works. Policies are machine-wide,
so with several profiles the profile launched last decides the policy values.

## Layout
`gui.py` window, `settings.py` paths/profiles layout, `profiles.py`, `transfer.py` export/import, `actions.py`,
`policies.py`, `extbuilder.py`, `launcher.py`, `branding.py`, `fetcher.py`, `ai.py`, `validate.py`, `mods.py`.

## Known limitations
- AI mods are content scripts (CSS/JS) only.
- Filter conversion covers common rules; 30,000 rule cap.
- Chrome Web Store installs are not supported yet (extension suggestions are shown for manual install).
- Auto-update of the browser is planned (GitHub releases).

## Choosing an ad blocker

Settings > Ad blocking > "Ad blocker to use":

- **uBlock Origin Lite** (recommended): downloaded from the official GitHub release, SHA-256 verified, loaded as an extension.
- **AdGuard (MV3)**: same, from AdGuard's releases.
- **uBlock Origin (full)**: Manifest V2, experimental; recent Chromium versions may refuse it.
- **Custom**: your own unpacked folder or .zip (only use extensions you trust).

If a download fails, the built-in blocker is used. Close the browser, press Apply, then Launch from the app or shortcut.

## Administrator, removing the browser, code signing

- The packaged exe always asks for administrator rights (needed for policy settings). When started from source it
  re-launches itself as administrator unless `CC_NO_ADMIN=1` is set. The browser itself is always started without
  administrator rights.
- Home > "Remove customized browser..." deletes the browser, its data, policies, shortcuts and downloaded extensions.
  ChromiumChanger and your settings are kept. Command line: `python -m chromiumchanger remove-browser`.
- Signing: `build_exe.bat` signs the exe when a certificate is available. Set `CC_SIGN_PFX` and `CC_SIGN_PASS`
  (a .pfx file) or `CC_SIGN_SUBJECT` (a certificate in the Windows store) before building. `signtool` comes with the
  Windows SDK ("Signing Tools for Desktop Apps"). A certificate has to be issued by a certificate authority
  (for example DigiCert, Sectigo, or Azure Trusted Signing); open-source projects can apply to SignPath Foundation.
  A self-made certificate signs the file but Windows will not trust it, so SmartScreen still warns.

## Updates via GitHub

1. Create a GitHub repository and push this folder (the `.gitignore` is included).
2. Put `owner/repo` into `UPDATE_REPO` in `chromiumchanger/updater.py` (or `"update_repo"` in app.json, or env `CC_UPDATE_REPO`).
3. To publish a version: `git tag v0.3.0` then `git push origin v0.3.0`. The workflow (copy `github-release-workflow.yml` to `.github/workflows/release.yml` in your repo)
   builds the exe on GitHub and attaches `ChromiumChanger-win64.zip` to a new release.
4. In the app, Home > "Check for updates" compares the tag with the installed version, downloads the zip, verifies its
   SHA-256, and installs it after the app closes (the app restarts by itself). Only the packaged exe can self-update.

## Code signing

Release builds are signed when the SignPath secrets are set (see `CODE_SIGNING.md`).

Free code signing provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org).

## License

MIT License (see the LICENSE file). ChromiumChanger downloads ungoogled-chromium, uBlock Origin Lite
and (optionally) Ollama at run time; they are not part of this repository and keep their own licenses.

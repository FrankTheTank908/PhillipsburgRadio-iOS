# Phillipsburg Radio iOS

Beginner setup guide for the Phillipsburg / Easton Public Safety iPhone scanner app.

You now have a RadioReference / Broadcastify API key, so the project uses the official API route.

## The New Simple Architecture

Current backend path:

```text
iPhone app
  -> asks http://franksplex.com:5214/current-feed.json
  -> polls http://franksplex.com:5214/transcripts

Raspberry Pi backend image
  -> listens on port 5214
  -> keeps your Broadcastify API key out of the iPhone app
  -> calls the official Broadcastify Audio API
  -> gets feed 45951 details
  -> builds the live stream URL from the API response
  -> returns safe JSON to the app
  -> serves transcript events

Broadcastify
  -> serves the actual live audio to listeners
```

Optional Cloudflare backup path:

```text
Cloudflare Worker
  -> can also keep your Broadcastify API key secret
  -> can serve /current-feed.json if you do not want the Pi exposed publicly
```

This saves your home bandwidth. Your house only uploads the normal feed to Broadcastify. App listeners pull audio from Broadcastify, not from your home.

## Important Security Note

Do not put your API key in:

- `AppConfig.swift`
- the iPhone app
- GitHub Actions
- README files
- screenshots in public places

Your API key should only go into GitHub Secrets for the Pi image build, or into Cloudflare as a Worker secret if you use the Cloudflare backup path.

Primary Pi image secret name:

```text
BROADCASTIFY_API_KEY
```

Cloudflare backup secret name:

```text
BROADCASTIFY_API_KEY
```

Because the key was visible in a screenshot, consider regenerating or rotating it later if RadioReference gives you that option.

The Raspberry Pi image artifact contains the API key because the image is preconfigured. Keep the GitHub repository private, do not share the Pi image artifact publicly, and delete old workflow artifacts if you rotate the key.

## What Is Included

- SwiftUI iOS app.
- `AVPlayer` in-app audio playback.
- Automatic retry if playback fails or stalls.
- Remote JSON config support.
- Live transcript polling from the Pi backend.
- Red `POLICE` app icon.
- GitHub Actions unsigned `.ipa` build.
- GitHub Actions Raspberry Pi backend image build.
- Raspberry Pi HTTP backend on port `5214`.
- Cloudflare Worker official Broadcastify API bridge.
- Raspberry Pi API backend service configured from GitHub Secrets at image build time.
- Old Raspberry Pi page scraper fallback, kept only as backup.

## Your Feed Info

Your public Broadcastify feed page is:

```text
https://www.broadcastify.com/listen/feed/45951
```

Feed ID:

```text
45951
```

The Worker config already uses this feed ID.

## Part 1: Put This Project On GitHub

If this repo is not already on GitHub:

1. Go to [GitHub](https://github.com).
2. Create a new repository named:

```text
PhillipsburgRadio-iOS
```

3. Upload/push this project.

If using GitHub Desktop:

```text
File -> Add local repository -> Publish repository
```

Your repo URL will look like:

```text
https://github.com/YOUR_GITHUB_USERNAME/PhillipsburgRadio-iOS.git
```

## Part 2: Create A Free Cloudflare Account

1. Go to [Cloudflare signup](https://dash.cloudflare.com/sign-up).
2. Create an account.
3. Verify your email.
4. You do not need to move your domain for the basic `workers.dev` setup.

Official docs:

- [Cloudflare Workers getting started](https://developers.cloudflare.com/workers/get-started/guide/)
- [Cloudflare KV getting started](https://developers.cloudflare.com/kv/get-started/)
- [Cloudflare Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/)

## Part 3: Install Node.js

Cloudflare uses a command tool called Wrangler. Wrangler runs with Node.js.

1. Go to [Node.js](https://nodejs.org).
2. Install the LTS version.
3. Open PowerShell.
4. Check it installed:

```powershell
node --version
npm --version
```

Both commands should print version numbers.

## Part 4: Deploy The Cloudflare Worker

Open PowerShell on your computer.

Go to the Worker folder:

```powershell
cd C:\Users\Frank\Documents\GitHub\PhillipsburgRadio-iOS\cloudflare-worker
```

Install the Worker tools:

```powershell
npm install
```

Login to Cloudflare:

```powershell
npx wrangler login
```

A browser window opens. Sign in and approve Wrangler.

Copy the example config:

```powershell
copy wrangler.toml.example wrangler.toml
```

Create Cloudflare KV storage:

```powershell
npx wrangler kv namespace create FEED_CONFIG
```

Cloudflare prints something like:

```text
[[kv_namespaces]]
binding = "FEED_CONFIG"
id = "abc123yourrealid"
```

Open the Worker config:

```powershell
notepad wrangler.toml
```

Replace this:

```text
id = "replace-with-your-kv-namespace-id"
```

with your real KV ID.

Confirm these lines are in `wrangler.toml`:

```text
BROADCASTIFY_FEED_ID = "45951"
CACHE_SECONDS = "60"
STREAM_URL_TTL_SECONDS = "300"
```

Save and close Notepad.

## Part 5: Add Your Broadcastify API Key Secret

In PowerShell, still inside:

```text
C:\Users\Frank\Documents\GitHub\PhillipsburgRadio-iOS\cloudflare-worker
```

Run:

```powershell
npx wrangler secret put BROADCASTIFY_API_KEY
```

When it asks for the value, paste your RadioReference / Broadcastify key from the approval email and press Enter.

Do not put quotes around it.

Optional backup admin token:

```powershell
$chars = "0123456789abcdef"
$token = -join (1..64 | ForEach-Object { $chars[(Get-Random -Minimum 0 -Maximum $chars.Length)] })
$token
npx wrangler secret put UPDATE_TOKEN
```

Paste the generated token when Wrangler asks. This token is only for manual fallback updates and `/refresh`.

## Part 6: Deploy And Test The Worker

Deploy:

```powershell
npx wrangler deploy
```

At the end, Wrangler prints your Worker URL. It will look like:

```text
https://phillipsburg-radio-feed-config.YOUR-SUBDOMAIN.workers.dev
```

Test health in your browser:

```text
https://phillipsburg-radio-feed-config.YOUR-SUBDOMAIN.workers.dev/health
```

Success looks like:

```json
{
  "ok": true,
  "mode": "broadcastify-api",
  "feedId": "45951"
}
```

Test the app JSON:

```text
https://phillipsburg-radio-feed-config.YOUR-SUBDOMAIN.workers.dev/current-feed.json
```

Success looks similar to:

```json
{
  "feedId": "45951",
  "title": "Phillipsburg / Easton Public Safety",
  "status": "online",
  "listeners": 5,
  "bitrate": 32,
  "streamUrl": "http://relay.broadcastify.com/...",
  "updatedAt": "2026-05-11T13:30:00.000Z",
  "expiresAt": "2026-05-11T13:35:00.000Z",
  "source": "broadcastify-audio-api",
  "message": null
}
```

The stream URL may not end in `.mp3`. That is okay. The Broadcastify API can return a relay host plus mount point; the Worker builds a playable audio URL from that.

## Optional: Use Your Own Domain

Your approval email mentions `Franksplex.com`. If the API key is domain-bound, the clean setup is to put the Worker on your domain, for example:

```text
https://radio.franksplex.com/current-feed.json
```

The basic `workers.dev` URL is easier for testing. If Broadcastify rejects it because of domain rules, move the Worker to a Cloudflare custom domain under `franksplex.com`.

## Part 7: Put The Worker JSON URL Into The iPhone App

Open:

```text
PhillipsburgRadio/AppConfig.swift
```

Find:

```swift
static let feedConfigURL = "http://franksplex.com:5214/current-feed.json"
```

That is the Pi backend URL. If you use Cloudflare instead, replace it with your Worker URL:

```swift
static let feedConfigURL = "https://phillipsburg-radio-feed-config.YOUR-SUBDOMAIN.workers.dev/current-feed.json"
```

Save the file.

Commit and push to GitHub.

With GitHub Desktop:

```text
Summary: Set Broadcastify API Worker URL
Commit to main
Push origin
```

With command line:

```bash
git add .
git commit -m "Use Broadcastify API worker feed config"
git push
```

## Part 8: Build The Unsigned iPhone IPA

GitHub Actions workflow:

```text
.github/workflows/build-ios.yml
```

It builds with signing disabled:

```text
CODE_SIGNING_ALLOWED=NO
CODE_SIGNING_REQUIRED=NO
CODE_SIGN_IDENTITY=""
```

Steps:

1. Go to your GitHub repo.
2. Click Actions.
3. Click Build unsigned iOS IPA.
4. Click Run workflow.
5. Wait for the green check mark.
6. Open the completed workflow run.
7. Download:

```text
PhillipsburgRadio-unsigned-ipa
```

Inside is:

```text
PhillipsburgRadio-unsigned.ipa
```

This IPA is unsigned. You still need to sign it yourself before installing it on your iPhone.

## What The iPhone App Does

1. Launches.
2. Fetches your backend JSON URL.
3. Reads `streamUrl`.
4. Plays it with `AVPlayer`.
5. Polls `/transcripts` from the same backend host.
6. Shows API status, listeners, bitrate, updated time, source, transcript rows, and debug URL.
7. If playback fails or stalls, it asks the backend for a fresh config using:

```text
?refresh=1
```

The backend caches API responses so every iPhone is not hammering Broadcastify.

## In-App Settings

The app has a gear button in the top-right corner.

Regular settings:

- Feed config URL
- Reset feed config URL to default
- Auto-play on launch
- Poll backend transcripts
- Show or hide stream URL on the main screen
- Automatic retry count
- Stall timeout before retry

Admin settings:

- Password-gated admin tools
- Verbose session logs
- Force refresh stream config
- Copy diagnostics
- Clear logs
- Reset public settings
- Change admin password
- View current player/feed/runtime state

Default admin password:

```text
change-me-admin
```

Change it before sharing a build with anyone else. This is a local debugging gate, not strong security. It keeps normal users away from debug controls, but it is not a substitute for server-side auth.

## Part 9: Build A Raspberry Pi Backend Image

This is the no-SSH path. The image is configured during GitHub Actions using GitHub Secrets. After the workflow builds the image, you flash it and boot the Pi.

The GitHub workflow is:

```text
.github/workflows/build-pi-backend-image.yml
```

It downloads the official Raspberry Pi OS Lite 64-bit image, mounts the image partitions on the GitHub runner, copies in the Phillipsburg backend, enables the systemd services, and repacks it as a flashable `.img.xz`.

This workflow does not use `pi-gen`. That avoids ARM emulation failures on GitHub-hosted runners.

Before running it, create this GitHub repository secret:

```text
BROADCASTIFY_API_KEY
```

Value:

```text
your RadioReference / Broadcastify API key
```

Optional GitHub repository secret:

```text
BACKEND_ADMIN_TOKEN
```

If you do not set `BACKEND_ADMIN_TOKEN`, the workflow generates one while building the image. Set it yourself if you want to know the token for admin POST requests.

Steps:

1. Go to your GitHub repo.
2. Click Settings.
3. Click Secrets and variables.
4. Click Actions.
5. Click New repository secret.
6. Add `BROADCASTIFY_API_KEY`.
7. Go to Actions.
8. Click Build Raspberry Pi backend image.
9. Click Run workflow.
10. Wait. The workflow downloads and repacks a full Raspberry Pi OS image, so it can take a while.
11. Download the artifact:

```text
phillipsburg-radio-backend-pi-image
```

The artifact contains:

```text
phillipsburg-radio-backend-pi.img.xz
```

Flash it with Raspberry Pi Imager:

1. Open Raspberry Pi Imager.
2. Choose your Pi model.
3. Choose OS.
4. Choose Use custom.
5. Select `phillipsburg-radio-backend-pi.img.xz`.
6. Choose your SD card.
7. Use Imager settings to configure Wi-Fi and SSH if needed.
8. Write the image.

No SD-card file editing is required if `BROADCASTIFY_API_KEY` was set as a GitHub secret before building.

Important first-boot notes:

- Ethernet is simplest. Plug the Pi into your router before first boot.
- If you need Wi-Fi, set Wi-Fi in Raspberry Pi Imager before writing the SD card.
- If you want SSH access, set a username and password in Raspberry Pi Imager before writing the SD card.
- The backend itself does not require you to SSH in after boot.

The backend config is also written to the boot partition as:

```text
phillipsburg-radio.env
```

If you ever need to fix the API key or admin token manually, shut down the Pi, put the SD card in your computer, open the visible boot drive, edit `phillipsburg-radio.env`, save it, and boot the Pi again.

The backend service runs every 60 seconds:

```text
phillipsburg-radio-backend.timer
```

The HTTP backend service runs continuously:

```text
phillipsburg-radio-server.service
```

It listens on:

```text
http://franksplex.com:5214
```

To make that public URL reach your Pi, your router must forward:

```text
TCP port 5214 -> Raspberry Pi local IP port 5214
```

After booting the Pi and setting the router port forward, test these in a browser:

```text
http://franksplex.com:5214/health
http://franksplex.com:5214/current-feed.json
```

`/health` should show `"service": "phillipsburg-radio-backend"`.

`/current-feed.json` should include a `streamUrl`.

Endpoints:

```text
GET  /health
GET  /current-feed.json
GET  /transcripts
GET  /events
POST /transcripts
POST /admin/refresh
GET  /admin/logs
```

The service writes current JSON to:

```text
/var/lib/phillipsburg-radio/current-feed.json
```

It stores transcript events in:

```text
/var/lib/phillipsburg-radio/transcripts.jsonl
```

## Raspberry Pi Scraper Is Fallback Only

You do not need the Pi to scrape Broadcastify anymore.

The Pi is still useful for:

- uploading your scanner audio to Broadcastify like normal
- future local transcription
- future keyword detection
- future cloud transcript uploads
- optional API-backed JSON uploader

The old Pi scraper files are still in:

```text
pi/
```

Keep them as emergency fallback only.

## iOS Project Details

- App name: `Phillipsburg Radio`
- Scheme: `PhillipsburgRadio`
- Bundle identifier: `com.frankpinheiro.phillipsburgradio`
- Deployment target: iOS 17.0
- UI framework: SwiftUI
- Audio framework: AVFoundation
- Player: AVPlayer
- Background audio mode: enabled
- App icon: included in `Assets.xcassets`
- HTTP media streams: allowed for media playback

The app should not crash if the Worker URL is wrong or the stream fails. It shows an error message and lets you refresh.

## Troubleshooting

If the Pi image workflow fails:

- Open the failed GitHub Actions run.
- Download the logs if GitHub uploads them.
- The current workflow should not show `pi-gen`, `debootstrap`, or `arm64: not supported`; if it does, your branch is still using the old workflow.

If `http://franksplex.com:5214/health` does not load:

- Confirm the Pi is powered on.
- Confirm the Pi is on your network.
- Confirm the router forwards TCP port `5214` to the Pi local IP.
- Try the Pi local address first, for example `http://192.168.1.50:5214/health`.
- Make sure your ISP/router allows inbound port forwarding.

If `/health` loads but `/current-feed.json` fails:

- Check the `BROADCASTIFY_API_KEY` GitHub Secret.
- Rebuild the Pi image after changing the secret.
- Or edit `phillipsburg-radio.env` on the SD card boot partition.

If the optional Cloudflare Worker `/health` does not show `broadcastify-api`:

```powershell
cd C:\Users\Frank\Documents\GitHub\PhillipsburgRadio-iOS\cloudflare-worker
npx wrangler secret put BROADCASTIFY_API_KEY
npx wrangler deploy
```

If `/current-feed.json` says the API refresh failed:

- Check that your key was pasted correctly into Cloudflare.
- Check that `BROADCASTIFY_FEED_ID = "45951"` is in `wrangler.toml`.
- Confirm the key is for Broadcastify live audio access, not only another RadioReference API.
- If the key is domain-bound, try putting the Worker under `franksplex.com`.

If GitHub Actions fails:

- Open the failed action.
- Read the red error text.
- Confirm the shared scheme exists:

```text
PhillipsburgRadio.xcodeproj/xcshareddata/xcschemes/PhillipsburgRadio.xcscheme
```

- Confirm the icon assets exist:

```text
PhillipsburgRadio/Assets.xcassets
```

If the IPA will not install:

- It is unsigned by design.
- Sign it first with your signing tool.
- Make sure the bundle identifier matches your signing profile.

## Later Upgrades

- Add Firebase, Supabase, or Cloudflare realtime transcript rows.
- Add transcript fields for timestamp, text, confidence, keywords, and channel/source.
- Add keyword notifications for Fire, EMS, MVA, structure fire, and other important calls.
- Add a Cloudflare custom domain under `franksplex.com`.

Recommended before branching beyond Phillipsburg / Easton:

- Add a remote app config field for maintenance mode and user-facing outage messages.
- Add a public incident timeline separate from raw transcript logs.
- Add favorites and region selection before supporting more feeds.
- Add a server-side admin panel instead of relying on hidden app-only admin controls.
- Add privacy/rules text explaining that the app rebroadcasts Broadcastify-provided audio and displays machine-generated transcripts that may be wrong.

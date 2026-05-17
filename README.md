# Phillipsburg Radio iOS

Beginner setup guide for the Phillipsburg / Easton Public Safety iPhone scanner app and Raspberry Pi backend.

This repo is now Pi-only for production:

```text
iPhone app
  -> http://franksplex.com:5214/current-feed.json
  -> http://franksplex.com:5214/transcripts
  -> http://franksplex.com:5214/incidents

Raspberry Pi backend
  -> listens on port 80 on the Pi
  -> is reached publicly through router port 5214
  -> keeps the Broadcastify domain key out of the iPhone app
  -> loads the official Broadcastify embed player for Franksplex.com
  -> calls the RadioReference SOAP database service for metadata
  -> serves the current Broadcastify stream URL to the app
  -> records short completed-call chunks for transcription
  -> cleans recorded audio with ffmpeg before transcription
  -> stores transcript events and grouped incidents for the app
  -> stores local incident chat notes for the app

Broadcastify
  -> serves the actual live audio to listeners

RadioReference
  -> serves database metadata, account data, feed names, feed IDs, systems, states, counties, agencies, frequencies, talkgroups, ZIP lookup, and FCC lookup through SOAP
```

There is no serverless backup path in this repo anymore. There is no Broadcastify page scraper path anymore.

## Known Decisions

- Public backend URL: `http://franksplex.com:5214`
- Pi internal backend port: `80`
- Router forwarding rule: external TCP `5214` -> Raspberry Pi local IP, internal TCP `80`
- Do not use `https://franksplex.com:5214` unless a real TLS reverse proxy is added later.
- The iOS app has an HTTP App Transport Security exception for `franksplex.com`; no SSL certificate is required for this personal build.
- Do not put the Broadcastify domain key in the iPhone app.
- Do not hard-code the rotating Broadcastify audio stream URL in the iPhone app.
- The Pi backend owns the Broadcastify embed-player request and returns safe JSON to the app.
- RadioReference SOAP metadata stays on the Pi backend and is exposed through safe JSON routes.
- Transcript and incident chat endpoints are local Pi storage.
- Completed-call transcription uses OpenAI only when `OPENAI_API_KEY` is present in the Pi image config.
- Do not run Broadcastify audio through AI/ML transcription unless your Broadcastify/RadioReference license allows that use.
- Live audio cleanup is not proxied through the Pi; cleanup is applied to recorded call chunks so the live player remains direct and low-latency.
- GitHub Actions builds the unsigned iPhone `.ipa`.
- GitHub Actions builds the flashable Raspberry Pi `.img.xz`.
- The old pi-gen image build broke on GitHub because ARM64 `debootstrap` could not execute reliably on the hosted runner.
- The current Pi image workflow avoids pi-gen and customizes the official Raspberry Pi OS Lite image directly.

## Your Feed

Feed name:

```text
Phillipsburg / Easton Public Safety
```

Broadcastify feed ID:

```text
45951
```

Public feed page:

```text
https://www.broadcastify.com/listen/feed/45951
```

App backend URL:

```text
http://franksplex.com:5214/current-feed.json
```

## Security Rules

Do not put your Broadcastify domain key in:

- `README.md`
- `AppConfig.swift`
- screenshots
- public GitHub issues
- the iPhone app

The domain key belongs in the GitHub repository secret named:

```text
BROADCASTIFY_API_KEY
```

The secret keeps the old name so the workflow does not need a new secret, but the value is your approved `Franksplex.com` domain key.

The backend admin token belongs in the GitHub repository secret named:

```text
BACKEND_ADMIN_TOKEN
```

For RadioReference database metadata, these optional GitHub repository secrets are used when present:

```text
RADIOREFERENCE_API_KEY
RADIOREFERENCE_USERNAME
RADIOREFERENCE_PASSWORD
```

If `RADIOREFERENCE_API_KEY` is not set, the Pi image workflow falls back to `BROADCASTIFY_API_KEY` for the RadioReference app key so your existing secret still works.

For completed-call transcripts and incident grouping, add:

```text
OPENAI_API_KEY
```

This personal debug build writes `ALLOW_DEBUG_ADMIN_WITHOUT_TOKEN=1`, so local app/admin POST routes do not need a password or token. Set that to `0` and use `BACKEND_ADMIN_TOKEN` before sharing a public build.

The Pi image artifact contains the domain key and any RadioReference secrets because it is preconfigured. Keep the repo private and do not share the Pi image artifact publicly.

## What Is Included

- SwiftUI iPhone app.
- AVFoundation / AVPlayer audio playback.
- Gear settings screen.
- Admin/debug settings screen unlocked for this personal build.
- Automatic stream refresh and retry.
- Recent completed-call incident transcripts from the Pi backend.
- ffmpeg recorded-audio cleanup for past incidents.
- Incident chat/notes backed by the Pi.
- Red `POLICE` app icon.
- Unsigned iOS IPA GitHub Actions workflow.
- Raspberry Pi backend image GitHub Actions workflow.
- Python Pi backend server on Pi port `80`, public port `5214`.
- Official Broadcastify embed-player/domain-key integration.
- RadioReference SOAP metadata integration.
- OpenAI transcription integration through `OPENAI_API_KEY`.

## Repo Layout

```text
.github/workflows/build-ios.yml
.github/workflows/build-pi-backend-image.yml
backend/
PhillipsburgRadio/
PhillipsburgRadio.xcodeproj/
config/current-feed.example.json
README.md
```

## Step 1: Set GitHub Secrets

Open your GitHub repo in a browser.

1. Click `Settings`.
2. Click `Secrets and variables`.
3. Click `Actions`.
4. Click `New repository secret`.
5. Add this secret:

```text
BROADCASTIFY_API_KEY
```

Value: your RadioReference / Broadcastify domain key.
Use the domain key from the approval email for `http://Franksplex.com`.

6. Click `New repository secret` again.
7. Optional: add RadioReference SOAP account secrets if your account requires them for metadata/account routes:

```text
RADIOREFERENCE_API_KEY
RADIOREFERENCE_USERNAME
RADIOREFERENCE_PASSWORD
```

8. Add this secret for automatic completed-call transcripts:

```text
OPENAI_API_KEY
```

9. Optional: add this secret if you later turn off debug admin mode:

```text
BACKEND_ADMIN_TOKEN
```

Value: your admin token.

Do not add quotes around secret values.

## Step 2: Build The Raspberry Pi Backend Image

Workflow:

```text
.github/workflows/build-pi-backend-image.yml
```

What it does:

1. Downloads the latest official Raspberry Pi OS Lite 64-bit image.
2. Mounts the image partitions on the GitHub runner.
3. Copies the backend Python files into `/opt/phillipsburg-radio/backend`.
4. Writes backend config to the SD card boot partition as `phillipsburg-radio.env`.
5. Enables the backend systemd services.
6. Compresses the finished image as `phillipsburg-radio-backend-pi.img.xz`.

Run it:

1. Go to your GitHub repo.
2. Click `Actions`.
3. Click `Build Raspberry Pi backend image`.
4. Click `Run workflow`.
5. Wait for it to finish.
6. Open the completed workflow run.
7. Download the artifact:

```text
phillipsburg-radio-backend-pi-image
```

Inside the artifact is:

```text
phillipsburg-radio-backend-pi.img.xz
```

## Step 3: Flash The Pi Image

Use Raspberry Pi Imager.

1. Open Raspberry Pi Imager.
2. Choose your Raspberry Pi model.
3. Click `Choose OS`.
4. Click `Use custom`.
5. Select `phillipsburg-radio-backend-pi.img.xz`.
6. Click `Choose Storage`.
7. Select the SD card.
8. Open Imager settings.
9. Configure Wi-Fi if you will not use Ethernet.
10. Enable SSH only if you want SSH access.
11. Set a username/password only if you enabled SSH.
12. Write the image.

Ethernet is preferred. If possible, plug Ethernet into the Pi before first boot.

First boot can take 5-10 minutes. Do not pull power during the first few minutes.

## Step 4: Router Port Forward

The app expects:

```text
http://franksplex.com:5214
```

Your router must forward:

```text
TCP 5214 -> Raspberry Pi local IP, port 80
```

Example:

```text
External port: 5214
Internal IP: 192.168.1.50
Internal port: 80
Protocol: TCP
```

Your Pi local IP will be different. Find it in your router device list.

## Step 5: Test The Pi Backend

From a device on your home network, test the local IP first:

```text
http://PI_LOCAL_IP/health
```

Example:

```text
http://192.168.1.50/health
```

Then test the public domain:

```text
http://franksplex.com:5214/health
```

Expected `/health` response includes:

```json
{
  "service": "phillipsburg-radio-backend",
  "feedId": "45951",
  "port": 80,
  "hasDomainKey": true,
  "hasApiKey": true,
  "hasRadioReferenceAuth": true,
  "hasOpenAIKey": true,
  "debugAdminNoAuth": true
}
```

Now test:

```text
http://franksplex.com:5214/current-feed.json
```

Expected response includes:

```json
{
  "feedId": "45951",
  "title": "Phillipsburg / Easton Public Safety",
  "streamUrl": "http://...",
  "updatedAt": "2026-05-17T00:00:00Z",
  "expiresAt": "2026-05-17T00:05:00Z",
  "source": "broadcastify-embed-player-pi-backend"
}
```

The `streamUrl` can be `http://` or `https://` because Broadcastify controls the audio relay. The app backend itself remains `http://franksplex.com:5214`.

## Pi Backend Endpoints

```text
GET  /health
GET  /current-feed.json
GET  /current-feed.json?refresh=1
GET  /metadata
GET  /transcripts
GET  /incidents
GET  /events
GET  /radio-reference/methods
GET  /radio-reference/countries
GET  /radio-reference/country?coid=1
GET  /radio-reference/state?stid=34
GET  /radio-reference/county?ctid=1778
GET  /radio-reference/zipcode?zipcode=08865
GET  /radio-reference/user-feeds
GET  /radio-reference/search?scope=county&ctid=1778&freq=155.000&tone=
POST /transcripts
POST /incidents
POST /admin/refresh
GET  /admin/logs
```

`GET /transcripts` returns completed scanner events, grouped incident summaries, and the transcript worker status:

```json
{
  "events": [],
  "incidents": [],
  "pipeline": {
    "state": "transcribed",
    "message": "Added transcript to inc-..."
  }
}
```

Admin endpoints require a token only when `ALLOW_DEBUG_ADMIN_WITHOUT_TOKEN=0`:

```text
Authorization: Bearer YOUR_BACKEND_ADMIN_TOKEN
```

or:

```text
X-Admin-Token: YOUR_BACKEND_ADMIN_TOKEN
```

## Pi Config File

The image writes this file to the visible SD card boot partition:

```text
phillipsburg-radio.env
```

It contains:

```text
BROADCASTIFY_API_KEY=
RADIOREFERENCE_API_KEY=
RADIOREFERENCE_USERNAME=
RADIOREFERENCE_PASSWORD=
RADIOREFERENCE_ENDPOINT=https://api.radioreference.com/soap2/
RADIOREFERENCE_VERSION=latest
RADIOREFERENCE_STYLE=rpc
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_TRANSCRIBE_MODEL=gpt-4o-transcribe
OPENAI_INCIDENT_MODEL=gpt-5.5
ENABLE_OPENAI_INCIDENT_ANALYSIS=1
BROADCASTIFY_FEED_ID=45951
BACKEND_BIND_HOST=0.0.0.0
BACKEND_PORT=80
PUBLIC_BASE_URL=http://franksplex.com:5214
BACKEND_ADMIN_TOKEN=
ALLOW_DEBUG_ADMIN_WITHOUT_TOKEN=1
BROADCASTIFY_EMBED_PLAYER_URL=https://api.broadcastify.com/embed/player/
BROADCASTIFY_REFERER=http://Franksplex.com/
INCIDENTS_PATH=/var/lib/phillipsburg-radio/incidents.jsonl
TRANSCRIPTS_PATH=/var/lib/phillipsburg-radio/transcripts.jsonl
INCIDENT_STATE_PATH=/var/lib/phillipsburg-radio/incident-state.json
PIPELINE_STATUS_PATH=/var/lib/phillipsburg-radio/transcript-pipeline-status.json
RECORDINGS_DIR=/var/lib/phillipsburg-radio/recordings
TRANSCRIPT_CHUNK_SECONDS=25
TRANSCRIPT_SLEEP_SECONDS=4
MIN_SPEECH_SECONDS=3
AUDIO_CLEANUP_FILTER=highpass=f=250,lowpass=f=3600,afftdn=nf=-28,loudnorm=I=-18:TP=-2:LRA=11
```

Normally you do not need to edit it because GitHub Actions writes the secrets into the image.

If you must edit it:

1. Shut down the Pi.
2. Remove the SD card.
3. Put it in your Windows computer.
4. Open the visible boot drive.
5. Open `phillipsburg-radio.env`.
6. Edit the value.
7. Save.
8. Put the SD card back into the Pi.
9. Boot the Pi.

## Step 6: Build The Unsigned iPhone IPA

Workflow:

```text
.github/workflows/build-ios.yml
```

It builds with signing disabled:

```text
CODE_SIGNING_ALLOWED=NO
CODE_SIGNING_REQUIRED=NO
CODE_SIGN_IDENTITY=""
```

Run it:

1. Go to your GitHub repo.
2. Click `Actions`.
3. Click `Build unsigned iOS IPA`.
4. Click `Run workflow`.
5. Wait for the green check mark.
6. Download the artifact:

```text
PhillipsburgRadio-unsigned-ipa
```

Inside is:

```text
PhillipsburgRadio-unsigned.ipa
```

This IPA is unsigned. Sign it yourself before installing it on your iPhone.

## iPhone App Defaults

Default feed config URL:

```text
http://franksplex.com:5214/current-feed.json
```

Source file:

```text
PhillipsburgRadio/AppConfig.swift
```

The app:

1. Opens.
2. Fetches `http://franksplex.com:5214/current-feed.json`.
3. Reads `streamUrl`.
4. Plays the Broadcastify audio stream with AVPlayer.
5. Polls `http://franksplex.com:5214/transcripts` for recent completed incidents.
6. Polls and posts `http://franksplex.com:5214/incidents`.
7. If playback fails or stalls, calls `current-feed.json?refresh=1`.

## In-App Settings

The gear button opens settings.

Regular settings:

- Feed config URL.
- Auto-play on launch.
- Poll backend transcripts.
- Show stream URL on main screen.
- Automatic retry count.
- Stall timeout.

Admin settings:

- Verbose session logs.
- Force refresh stream config.
- Copy diagnostics.
- Clear logs.
- Reset public settings.
- View player/feed/runtime state.

This personal build does not ask for a local admin password because:

```text
AppConfig.requiresAdminPassword = false
```

Set `AppConfig.requiresAdminPassword = true` before sharing Release builds outside your own devices.

## Troubleshooting

If the Pi image workflow mentions `pi-gen`, `debootstrap`, or `arm64: not supported`, your branch is running the old workflow. Pull or push the latest repo changes and run it again.

If `http://franksplex.com:5214/health` does not load:

- Test the Pi local IP first.
- Confirm the Pi has power.
- Confirm Ethernet or Wi-Fi is connected.
- Confirm the router forwards external TCP port `5214` to Pi internal TCP port `80`.
- Confirm your public DNS for `franksplex.com` points to your home public IP.
- Confirm your ISP/router allows inbound port forwarding.

If `/health` loads but `/current-feed.json` fails:

- Confirm the GitHub secret `BROADCASTIFY_API_KEY` exists and contains the approved `Franksplex.com` domain key.
- Rebuild and reflash the Pi image after changing the secret.
- Or edit `phillipsburg-radio.env` on the SD card boot partition.

If `/transcripts` keeps showing no completed incidents:

- Check `http://franksplex.com:5214/health` and confirm `hasOpenAIKey` is `true`.
- Confirm the Pi has installed `ffmpeg`; the transcript service installs it automatically on first start.
- Wait until there is actual scanner traffic. Silent chunks are skipped.
- Check `transcriptPipeline.message` in `/health` or the `pipeline` object in `/transcripts`.

If the iPhone app launches but does not play:

- Open settings and confirm the feed URL is exactly:

```text
http://franksplex.com:5214/current-feed.json
```

- Test that same URL in Safari.
- Tap `Refresh URL`.
- Check admin diagnostics.

If the IPA will not install:

- The IPA is unsigned by design.
- Sign it first.
- Make sure the bundle identifier matches your signing profile.

## Later Work

- Add keyword notifications for fire, EMS, MVA, and major incidents.
- Add a real admin web panel on the Pi.
- Add a privacy/disclaimer page before App Store submission.
- Add App Store signing/archive workflow later when you are ready.

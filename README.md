# Phillipsburg Radio iOS

Starter SwiftUI iOS app for a Police & Fire Phillipsburg radio feed.

## What this app does right now

- Fetches a tiny remote JSON config file.
- Reads the current Broadcastify `.mp3` stream URL from that JSON.
- Plays the stream with `AVPlayer` inside the app.
- Has a Refresh button to fetch a new stream URL if the old `.mp3` expires.
- Includes a placeholder Live Transcript section for later Firebase/Supabase integration.
- Includes a GitHub Actions workflow to build an unsigned `.ipa` artifact.

## JSON file format

Create a URL that returns this JSON:

```json
{
  "streamUrl": "https://your-current-broadcastify-stream-url.mp3",
  "updatedAt": "2026-05-10T23:45:00Z",
  "message": "Optional note"
}
```

Then edit:

```swift
PhillipsburgRadio/AppConfig.swift
```

Replace:

```swift
static let feedConfigURL = "https://example.com/current-feed.json"
```

with your real JSON URL.

## Build unsigned IPA with GitHub Actions

1. Upload this repo to GitHub.
2. Go to the repo on GitHub.
3. Click **Actions**.
4. Click **Build unsigned iOS IPA**.
5. Click **Run workflow**.
6. Download the artifact named `PhillipsburgRadio-unsigned-ipa`.

The output file will be:

```text
PhillipsburgRadio-unsigned.ipa
```

You can then sign it yourself using your own signing method.

## Change bundle identifier

The default bundle identifier is:

```text
com.frankpinheiro.phillipsburgradio
```

You can change it in:

```text
PhillipsburgRadio.xcodeproj/project.pbxproj
```

Search for:

```text
PRODUCT_BUNDLE_IDENTIFIER
```

## Notes

This starter is intentionally simple. The next pieces to add are:

- Cloudflare Worker/KV for the current audio URL.
- Raspberry Pi script to update the current URL automatically.
- Firebase or Supabase for live transcript events.
- Push notifications for keywords like Fire, EMS, MVA, structure fire, etc.

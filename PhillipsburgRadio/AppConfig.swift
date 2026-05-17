import Foundation

enum AppConfig {
    // Replace this with your hosted JSON URL from Cloudflare, Firebase,
    // Supabase, or another small config endpoint. Do not put the rotating
    // Broadcastify .mp3 URL directly in the app.
    //
    // The URL should return JSON like:
    // {
    //   "feedId": "phillipsburg_easton_public_safety",
    //   "streamUrl": "https://example.com/current-feed.mp3",
    //   "updatedAt": "2026-05-10T23:45:00Z",
    //   "expiresAt": "2026-05-10T23:50:00Z",
    //   "source": "broadcastify-page-resolver"
    // }
    static let feedConfigURL = "http://franksplex.com:5214/current-feed.json"

    static let appTitle = "Phillipsburg Radio"
    static let feedTitle = "Phillipsburg / Easton Public Safety"
    static let subtitle = "Broadcastify audio with live transcript support"
    static let automaticRetryLimit = 2
    static let stallRecoverySeconds = 12
    static let defaultAdminPassword = "change-me-admin"
}

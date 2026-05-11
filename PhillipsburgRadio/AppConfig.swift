import Foundation

enum AppConfig {
    // Replace this with your Cloudflare Worker / Firebase / JSON URL.
    // The URL should return JSON like:
    // {
    //   "streamUrl": "https://example.com/current-feed.mp3",
    //   "updatedAt": "2026-05-10T23:45:00Z"
    // }
    static let feedConfigURL = "https://example.com/current-feed.json"

    static let appTitle = "Phillipsburg Radio"
    static let feedTitle = "Police & Fire Phillipsburg"
    static let subtitle = "Live scanner audio with transcript support"
}

import Foundation

enum AppConfig {
    // Pi-only production endpoint. Do not put the Broadcastify domain key or a
    // rotating Broadcastify stream URL directly in the iPhone app.
    //
    // The Pi returns JSON like:
    // {
    //   "feedId": "45951",
    //   "streamUrl": "https://relay.broadcastify.com/example",
    //   "updatedAt": "2026-05-10T23:45:00Z",
    //   "expiresAt": "2026-05-10T23:50:00Z",
    //   "source": "broadcastify-embed-player-pi-backend"
    // }
    static let feedConfigURL = Bundle.main.stringValue(
        forInfoDictionaryKey: "FeedConfigURL",
        fallback: "http://example.invalid/current-feed.json"
    )

    static let appTitle = "Police Scanner"
    static let feedTitle = "Worldwide Scanner"
    static let subtitle = "Browse live public-safety audio by country, state, and county"
    static let premiumProductID = Bundle.main.stringValue(
        forInfoDictionaryKey: "PremiumProductID",
        fallback: "com.frankpinheiro.scanner.premium.monthly"
    )
    static let adMobRewardedAdUnitID = Bundle.main.stringValue(
        forInfoDictionaryKey: "AdMobRewardedAdUnitID",
        fallback: ""
    )
    static let automaticRetryLimit = 2
    static let stallRecoverySeconds = 12
    // Personal debug build: admin tools are visible without a password.
    // Set this to true before sharing a Release build outside your own devices.
    static let requiresAdminPassword = false
    static let defaultAdminPassword = "change-me-admin"
}

private extension Bundle {
    func stringValue(forInfoDictionaryKey key: String, fallback: String) -> String {
        let value = object(forInfoDictionaryKey: key) as? String
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if trimmed.isEmpty || trimmed.contains("$(") {
            return fallback
        }
        return trimmed
    }
}

import Foundation
import Combine

struct PlayerSettingsSnapshot: Equatable {
    let feedConfigURL: String
    let automaticRetryLimit: Int
    let stallRecoverySeconds: Int
    let enableVerboseLogs: Bool

    static let `default` = PlayerSettingsSnapshot(
        feedConfigURL: AppConfig.feedConfigURL,
        automaticRetryLimit: AppConfig.automaticRetryLimit,
        stallRecoverySeconds: AppConfig.stallRecoverySeconds,
        enableVerboseLogs: false
    )
}

@MainActor
final class SettingsStore: ObservableObject {
    @Published var feedConfigURL: String {
        didSet { defaults.set(feedConfigURL, forKey: Keys.feedConfigURL) }
    }

    @Published var autoPlayOnLaunch: Bool {
        didSet { defaults.set(autoPlayOnLaunch, forKey: Keys.autoPlayOnLaunch) }
    }

    @Published var showStreamURLOnMain: Bool {
        didSet { defaults.set(showStreamURLOnMain, forKey: Keys.showStreamURLOnMain) }
    }

    @Published var enableVerboseLogs: Bool {
        didSet { defaults.set(enableVerboseLogs, forKey: Keys.enableVerboseLogs) }
    }

    @Published var enableTranscriptPolling: Bool {
        didSet { defaults.set(enableTranscriptPolling, forKey: Keys.enableTranscriptPolling) }
    }

    @Published var automaticRetryLimit: Int {
        didSet { defaults.set(automaticRetryLimit, forKey: Keys.automaticRetryLimit) }
    }

    @Published var stallRecoverySeconds: Int {
        didSet { defaults.set(stallRecoverySeconds, forKey: Keys.stallRecoverySeconds) }
    }

    @Published private(set) var isAdminUnlocked = false

    private let defaults: UserDefaults

    var playerSettings: PlayerSettingsSnapshot {
        PlayerSettingsSnapshot(
            feedConfigURL: trimmedFeedConfigURL,
            automaticRetryLimit: automaticRetryLimit,
            stallRecoverySeconds: stallRecoverySeconds,
            enableVerboseLogs: enableVerboseLogs
        )
    }

    var trimmedFeedConfigURL: String {
        feedConfigURL.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults

        feedConfigURL = defaults.string(forKey: Keys.feedConfigURL) ?? AppConfig.feedConfigURL
        autoPlayOnLaunch = defaults.object(forKey: Keys.autoPlayOnLaunch) as? Bool ?? false
        showStreamURLOnMain = defaults.object(forKey: Keys.showStreamURLOnMain) as? Bool ?? false
        enableVerboseLogs = defaults.object(forKey: Keys.enableVerboseLogs) as? Bool ?? false
        enableTranscriptPolling = defaults.object(forKey: Keys.enableTranscriptPolling) as? Bool ?? true

        let savedRetryLimit = defaults.object(forKey: Keys.automaticRetryLimit) as? Int
        automaticRetryLimit = savedRetryLimit ?? AppConfig.automaticRetryLimit

        let savedStallSeconds = defaults.object(forKey: Keys.stallRecoverySeconds) as? Int
        stallRecoverySeconds = savedStallSeconds ?? AppConfig.stallRecoverySeconds

        if defaults.string(forKey: Keys.adminPassword) == nil {
            defaults.set(AppConfig.defaultAdminPassword, forKey: Keys.adminPassword)
        }
    }

    func unlockAdmin(password: String) -> Bool {
        let expected = defaults.string(forKey: Keys.adminPassword) ?? AppConfig.defaultAdminPassword
        let didUnlock = password == expected
        isAdminUnlocked = didUnlock
        return didUnlock
    }

    func lockAdmin() {
        isAdminUnlocked = false
    }

    func changeAdminPassword(to newPassword: String) -> Bool {
        let trimmed = newPassword.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 6 else {
            return false
        }

        defaults.set(trimmed, forKey: Keys.adminPassword)
        return true
    }

    func resetPublicSettings() {
        feedConfigURL = AppConfig.feedConfigURL
        autoPlayOnLaunch = false
        showStreamURLOnMain = false
        enableTranscriptPolling = true
        automaticRetryLimit = AppConfig.automaticRetryLimit
        stallRecoverySeconds = AppConfig.stallRecoverySeconds
    }

    private enum Keys {
        static let feedConfigURL = "settings.feedConfigURL"
        static let autoPlayOnLaunch = "settings.autoPlayOnLaunch"
        static let showStreamURLOnMain = "settings.showStreamURLOnMain"
        static let enableVerboseLogs = "settings.enableVerboseLogs"
        static let enableTranscriptPolling = "settings.enableTranscriptPolling"
        static let automaticRetryLimit = "settings.automaticRetryLimit"
        static let stallRecoverySeconds = "settings.stallRecoverySeconds"
        static let adminPassword = "settings.adminPassword"
    }
}

import Foundation
import Combine

struct AppLogEntry: Identifiable {
    let id = UUID()
    let date: Date
    let level: String
    let message: String
}

@MainActor
final class AppLogStore: ObservableObject {
    @Published private(set) var entries: [AppLogEntry] = []

    private let maxEntries = 250
    private let formatter: DateFormatter

    init() {
        formatter = DateFormatter()
        formatter.dateStyle = .none
        formatter.timeStyle = .medium
    }

    func info(_ message: String) {
        append(level: "info", message: message)
    }

    func warning(_ message: String) {
        append(level: "warning", message: message)
    }

    func error(_ message: String) {
        append(level: "error", message: message)
    }

    func clear() {
        entries.removeAll()
    }

    func diagnosticText(player: RadioPlayer, settings: SettingsStore) -> String {
        let lines = [
            "Phillipsburg Radio Diagnostics",
            "App title: \(AppConfig.appTitle)",
            "Feed title: \(AppConfig.feedTitle)",
            "Config URL: \(settings.trimmedFeedConfigURL)",
            "Status: \(player.statusText)",
            "Feed ID: \(player.feedId)",
            "API status: \(player.apiStatus)",
            "Listeners: \(player.listenerCount)",
            "Bitrate: \(player.bitrate)",
            "Updated: \(player.lastUpdated)",
            "Expires: \(player.expiresAt)",
            "Source: \(player.source)",
            "Stream URL: \(player.currentStreamURL.isEmpty ? "not loaded" : player.currentStreamURL)",
            "Last error: \(player.errorMessage ?? "none")",
            "",
            "Session logs:",
            formattedEntries()
        ]

        return lines.joined(separator: "\n")
    }

    private func append(level: String, message: String) {
        entries.insert(AppLogEntry(date: Date(), level: level, message: message), at: 0)

        if entries.count > maxEntries {
            entries.removeLast(entries.count - maxEntries)
        }
    }

    private func formattedEntries() -> String {
        if entries.isEmpty {
            return "No logs yet."
        }

        return entries
            .reversed()
            .map { "[\(formatter.string(from: $0.date))] \($0.level.uppercased()): \($0.message)" }
            .joined(separator: "\n")
    }
}

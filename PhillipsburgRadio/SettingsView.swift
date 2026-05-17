import SwiftUI
import UIKit

struct SettingsView: View {
    @ObservedObject var settingsStore: SettingsStore
    @ObservedObject var logStore: AppLogStore
    @ObservedObject var radioPlayer: RadioPlayer

    @Environment(\.dismiss) private var dismiss
    @State private var adminPassword = ""
    @State private var newAdminPassword = ""
    @State private var adminMessage: String?
    @State private var didCopyDiagnostics = false

    var body: some View {
        NavigationStack {
            Form {
                appSection
                playbackSection
                privacySection
                adminSection
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
    }

    private var appSection: some View {
        Section {
            TextField("Feed config URL", text: $settingsStore.feedConfigURL, axis: .vertical)
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
                .autocorrectionDisabled()

            Button("Reset to default URL") {
                settingsStore.feedConfigURL = AppConfig.feedConfigURL
                logStore.info("Feed config URL reset to default")
            }
        } header: {
            Text("Feed Config")
        } footer: {
            Text("This URL should point to the Pi backend JSON endpoint. The app never needs your Broadcastify API key.")
        }
    }

    private var playbackSection: some View {
        Section {
            Toggle("Auto-play on app launch", isOn: $settingsStore.autoPlayOnLaunch)
            Toggle("Poll backend transcripts", isOn: $settingsStore.enableTranscriptPolling)
            Toggle("Show stream URL on main screen", isOn: $settingsStore.showStreamURLOnMain)

            Stepper(value: $settingsStore.automaticRetryLimit, in: 0...8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Automatic retries")
                    Text("\(settingsStore.automaticRetryLimit)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Stepper(value: $settingsStore.stallRecoverySeconds, in: 5...45) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Stall timeout")
                    Text("\(settingsStore.stallRecoverySeconds) seconds")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        } header: {
            Text("Playback")
        }
    }

    private var privacySection: some View {
        Section {
            Label("API key stays on the Pi backend, not in this app.", systemImage: "lock.shield")
            Label("Admin unlock is a local debugging gate, not strong security.", systemImage: "exclamationmark.triangle")
        } header: {
            Text("Security")
        }
    }

    private var adminSection: some View {
        Section {
            if settingsStore.isAdminUnlocked {
                adminUnlockedContent
            } else {
                SecureField("Admin password", text: $adminPassword)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()

                Button {
                    unlockAdmin()
                } label: {
                    Label("Unlock Admin Tools", systemImage: "lock.open")
                }

                if let adminMessage {
                    Text(adminMessage)
                        .font(.footnote)
                        .foregroundStyle(.red)
                }
            }
        } header: {
            Text("Admin")
        } footer: {
            Text("Default password is set in AppConfig.swift. Change it before sharing builds outside your own testing.")
        }
    }

    private var adminUnlockedContent: some View {
        Group {
            Toggle("Verbose session logs", isOn: $settingsStore.enableVerboseLogs)

            Button {
                Task { await radioPlayer.refreshAndRetry(using: settingsStore.playerSettings) }
            } label: {
                Label("Force Refresh Stream Config", systemImage: "arrow.clockwise")
            }

            Button {
                copyDiagnostics()
            } label: {
                Label(didCopyDiagnostics ? "Diagnostics Copied" : "Copy Diagnostics", systemImage: "doc.on.doc")
            }

            Button(role: .destructive) {
                logStore.clear()
                logStore.info("Logs cleared")
            } label: {
                Label("Clear Logs", systemImage: "trash")
            }

            Button(role: .destructive) {
                settingsStore.resetPublicSettings()
                logStore.warning("Public settings reset")
            } label: {
                Label("Reset Public Settings", systemImage: "arrow.counterclockwise")
            }

            SecureField("New admin password", text: $newAdminPassword)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()

            Button("Save New Admin Password") {
                saveAdminPassword()
            }

            Button("Lock Admin Tools") {
                settingsStore.lockAdmin()
                adminPassword = ""
                newAdminPassword = ""
                adminMessage = nil
            }

            if let adminMessage {
                Text(adminMessage)
                    .font(.footnote)
                    .foregroundStyle(adminMessage.lowercased().contains("saved") ? .green : .red)
            }

            adminStatusSection
            adminLogsSection
        }
    }

    private var adminStatusSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Current Runtime")
                .font(.headline)

            adminValue("Player", radioPlayer.statusText)
            adminValue("Feed ID", radioPlayer.feedId)
            adminValue("API status", radioPlayer.apiStatus)
            adminValue("Listeners", radioPlayer.listenerCount)
            adminValue("Bitrate", radioPlayer.bitrate)
            adminValue("Updated", radioPlayer.lastUpdated)
            adminValue("Source", radioPlayer.source)
            adminValue("Last error", radioPlayer.errorMessage ?? "none")
        }
        .padding(.vertical, 4)
    }

    private var adminLogsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Session Logs")
                .font(.headline)

            if logStore.entries.isEmpty {
                Text("No logs yet.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(Array(logStore.entries.prefix(60))) { entry in
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(entry.level.uppercased()) \(entry.date.formatted(date: .omitted, time: .standard))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(entry.message)
                            .font(.footnote)
                            .textSelection(.enabled)
                    }
                    .padding(.vertical, 2)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func adminValue(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.footnote)
                .textSelection(.enabled)
        }
    }

    private func unlockAdmin() {
        if settingsStore.unlockAdmin(password: adminPassword) {
            adminMessage = nil
            logStore.warning("Admin tools unlocked")
        } else {
            adminMessage = "Wrong admin password."
            logStore.warning("Failed admin unlock attempt")
        }
    }

    private func saveAdminPassword() {
        if settingsStore.changeAdminPassword(to: newAdminPassword) {
            adminMessage = "Admin password saved."
            newAdminPassword = ""
            logStore.warning("Admin password changed")
        } else {
            adminMessage = "Use at least 6 characters."
        }
    }

    private func copyDiagnostics() {
        UIPasteboard.general.string = logStore.diagnosticText(player: radioPlayer, settings: settingsStore)
        didCopyDiagnostics = true
        logStore.info("Diagnostics copied")
    }
}

#Preview {
    SettingsView(
        settingsStore: SettingsStore(),
        logStore: AppLogStore(),
        radioPlayer: RadioPlayer()
    )
}

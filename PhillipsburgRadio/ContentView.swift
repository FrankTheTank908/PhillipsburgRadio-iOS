import SwiftUI

struct ContentView: View {
    @StateObject private var radioPlayer = RadioPlayer()
    @StateObject private var settingsStore = SettingsStore()
    @StateObject private var logStore = AppLogStore()
    @StateObject private var transcriptStore = TranscriptStore()
    @StateObject private var incidentStore = IncidentStore()
    @State private var isShowingSettings = false
    @State private var didAutoStart = false
    @State private var incidentDraft = ""

    private let sampleTranscripts: [TranscriptEvent] = [
        TranscriptEvent(
            timestamp: "--:--",
            text: "Waiting for live transcript events from your Pi backend.",
            keywords: ["placeholder"],
            channel: "Dispatch"
        ),
        TranscriptEvent(
            timestamp: "--:--",
            text: "Audio comes from the current Broadcastify stream URL resolved by the Pi.",
            keywords: ["audio", "broadcastify"],
            channel: "Feed"
        ),
        TranscriptEvent(
            timestamp: "--:--",
            text: "Future rows can include timestamp, text, confidence, keywords, and source channel.",
            confidence: 0.92,
            keywords: ["future", "transcript"],
            channel: "Pi"
        )
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    headerSection
                    playerSection
                    streamConfigSection
                    transcriptSection
                    incidentSection
                }
                .padding(16)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle(AppConfig.appTitle)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        isShowingSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                    .accessibilityLabel("Settings")
                }
            }
            .sheet(isPresented: $isShowingSettings) {
                SettingsView(
                    settingsStore: settingsStore,
                    logStore: logStore,
                    radioPlayer: radioPlayer
                )
            }
            .onAppear {
                radioPlayer.attachLogger(logStore)
                transcriptStore.attachLogger(logStore)
                incidentStore.attachLogger(logStore)
                configureTranscriptPolling()
                configureIncidentPolling()

                guard settingsStore.autoPlayOnLaunch, !didAutoStart else {
                    return
                }

                didAutoStart = true
                Task { await radioPlayer.start(using: settingsStore.playerSettings) }
            }
            .onChange(of: settingsStore.feedConfigURL) { _ in
                configureTranscriptPolling()
                configureIncidentPolling()
            }
            .onChange(of: settingsStore.enableTranscriptPolling) { _ in
                configureTranscriptPolling()
            }
        }
    }

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(AppConfig.feedTitle)
                .font(.largeTitle)
                .fontWeight(.bold)
                .lineLimit(2)
                .minimumScaleFactor(0.8)

            Text(AppConfig.subtitle)
                .font(.subheadline)
                .foregroundStyle(.secondary)

            Label("32 kbps Broadcastify feed", systemImage: "dot.radiowaves.left.and.right")
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 8)
    }

    private var playerSection: some View {
        panel {
            VStack(alignment: .leading, spacing: 14) {
                sectionTitle("Audio Player", systemImage: "speaker.wave.2.fill")

                HStack(spacing: 10) {
                    Button {
                        radioPlayer.playOrStop(using: settingsStore.playerSettings)
                    } label: {
                        Label(playButtonTitle, systemImage: playButtonIcon)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)

                    Button {
                        Task { await radioPlayer.refreshAndRetry(using: settingsStore.playerSettings) }
                    } label: {
                        Label("Refresh URL", systemImage: "arrow.clockwise")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                }
                .controlSize(.large)
                .lineLimit(1)
                .minimumScaleFactor(0.82)

                HStack(spacing: 10) {
                    if radioPlayer.isLoading {
                        ProgressView()
                    } else {
                        Image(systemName: statusIcon)
                            .foregroundStyle(statusColor)
                    }

                    Text(radioPlayer.statusText)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(minHeight: 28)

                if let error = radioPlayer.errorMessage {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private var streamConfigSection: some View {
        panel {
            VStack(alignment: .leading, spacing: 12) {
                sectionTitle("Current Stream Config", systemImage: "link")

                configRow("Feed", value: radioPlayer.feedId, systemImage: "antenna.radiowaves.left.and.right")
                configRow("API Status", value: radioPlayer.apiStatus, systemImage: "checkmark.seal")
                configRow("Listeners", value: radioPlayer.listenerCount, systemImage: "person.2")
                configRow("Bitrate", value: radioPlayer.bitrate, systemImage: "waveform")
                configRow("Updated", value: radioPlayer.lastUpdated, systemImage: "clock")
                configRow("Expires", value: radioPlayer.expiresAt, systemImage: "timer")
                configRow("Source", value: radioPlayer.source, systemImage: "server.rack")

                if settingsStore.showStreamURLOnMain {
                    DisclosureGroup("Debug stream URL") {
                        Text(radioPlayer.currentStreamURL.isEmpty ? "No stream URL loaded yet." : radioPlayer.currentStreamURL)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.top, 8)
                    }
                    .font(.footnote)
                }
            }
        }
    }

    private var transcriptSection: some View {
        panel {
            VStack(alignment: .leading, spacing: 12) {
                sectionTitle("Live Transcript", systemImage: "text.bubble")

                if let error = transcriptStore.lastError, settingsStore.enableTranscriptPolling {
                    Text("Transcript backend not reachable: \(error)")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                ForEach(transcriptRows) { event in
                    transcriptRow(event)

                    if event.id != transcriptRows.last?.id {
                        Divider()
                    }
                }
            }
        }
    }

    private var incidentSection: some View {
        panel {
            VStack(alignment: .leading, spacing: 12) {
                sectionTitle("Incident Chat", systemImage: "bubble.left.and.text.bubble.right")

                HStack(alignment: .top, spacing: 8) {
                    TextField("Add an incident note", text: $incidentDraft, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                        .lineLimit(1...3)

                    Button {
                        sendIncident()
                    } label: {
                        if incidentStore.isSending {
                            ProgressView()
                        } else {
                            Image(systemName: "paperplane.fill")
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(incidentDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || incidentStore.isSending)
                    .accessibilityLabel("Send incident note")
                }

                if let error = incidentStore.lastError {
                    Text("Incident chat backend not reachable: \(error)")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                if incidentStore.messages.isEmpty {
                    Text("No incident notes yet.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(incidentStore.messages) { message in
                        incidentRow(message)

                        if message.id != incidentStore.messages.last?.id {
                            Divider()
                        }
                    }
                }
            }
        }
    }

    private var playButtonTitle: String {
        radioPlayer.isPlaying || radioPlayer.isLoading ? "Stop" : "Play"
    }

    private var playButtonIcon: String {
        radioPlayer.isPlaying || radioPlayer.isLoading ? "stop.fill" : "play.fill"
    }

    private var transcriptRows: [TranscriptEvent] {
        transcriptStore.events.isEmpty ? sampleTranscripts : transcriptStore.events
    }

    private var statusIcon: String {
        if radioPlayer.isPlaying {
            return "checkmark.circle.fill"
        }

        if radioPlayer.errorMessage != nil {
            return "exclamationmark.triangle.fill"
        }

        return "pause.circle.fill"
    }

    private var statusColor: Color {
        if radioPlayer.isPlaying {
            return .green
        }

        if radioPlayer.errorMessage != nil {
            return .red
        }

        return .secondary
    }

    private func panel<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
            .background(Color(.secondarySystemGroupedBackground))
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private func sectionTitle(_ text: String, systemImage: String) -> some View {
        Label(text, systemImage: systemImage)
            .font(.headline)
    }

    private func configRow(_ title: String, value: String, systemImage: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: systemImage)
                .frame(width: 20)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.footnote)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func transcriptRow(_ event: TranscriptEvent) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(event.timestamp)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if let channel = event.channel {
                    Label(channel, systemImage: "waveform")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer(minLength: 8)

                if let confidence = event.confidence {
                    Text("\(Int(confidence * 100))%")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Text(event.text)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)

            if !event.keywords.isEmpty {
                Text(event.keywords.joined(separator: " | "))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }

    private func incidentRow(_ message: IncidentMessage) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(message.timestamp)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Label(message.author, systemImage: "person.crop.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Spacer(minLength: 8)
            }

            Text(message.text)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)

            if !message.tags.isEmpty {
                Text(message.tags.joined(separator: " | "))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }

    private func configureTranscriptPolling() {
        if settingsStore.enableTranscriptPolling {
            transcriptStore.startPolling(feedConfigURL: settingsStore.trimmedFeedConfigURL)
        } else {
            transcriptStore.stopPolling()
        }
    }

    private func configureIncidentPolling() {
        incidentStore.startPolling(feedConfigURL: settingsStore.trimmedFeedConfigURL)
    }

    private func sendIncident() {
        let text = incidentDraft
        Task {
            if await incidentStore.send(text: text, feedConfigURL: settingsStore.trimmedFeedConfigURL) {
                incidentDraft = ""
            }
        }
    }
}

#Preview {
    ContentView()
}

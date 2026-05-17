import SwiftUI

struct ContentView: View {
    @StateObject private var radioPlayer = RadioPlayer()
    @StateObject private var settingsStore = SettingsStore()
    @StateObject private var logStore = AppLogStore()
    @StateObject private var transcriptStore = TranscriptStore()
    @StateObject private var incidentStore = IncidentStore()
    @StateObject private var catalogStore = ScannerCatalogStore()
    @StateObject private var monetizationStore = MonetizationStore()
    @StateObject private var rewardedAdStore = RewardedAdStore()
    @State private var isShowingSettings = false
    @State private var isShowingAccessGate = false
    @State private var didAutoStart = false
    @State private var incidentDraft = ""
    @State private var selectedFeed: CatalogItem?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    headerSection
                    catalogSection
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
            .sheet(isPresented: $isShowingAccessGate) {
                accessGateSheet
            }
            .onAppear {
                radioPlayer.attachLogger(logStore)
                transcriptStore.attachLogger(logStore)
                incidentStore.attachLogger(logStore)
                catalogStore.attachLogger(logStore)
                monetizationStore.attachLogger(logStore)
                configureTranscriptPolling()
                configureIncidentPolling()
                Task {
                    await catalogStore.loadCountries(feedConfigURL: settingsStore.trimmedFeedConfigURL)
                    await monetizationStore.refreshEntitlements(feedConfigURL: settingsStore.trimmedFeedConfigURL)
                    await rewardedAdStore.preload(
                        adUnitID: AppConfig.adMobRewardedAdUnitID,
                        customData: rewardCustomData
                    )
                }

                guard settingsStore.autoPlayOnLaunch, !didAutoStart else {
                    return
                }

                didAutoStart = true
                Task {
                    await monetizationStore.refreshEntitlements(feedConfigURL: settingsStore.trimmedFeedConfigURL)
                    if monetizationStore.canPlay {
                        await startPlaybackForSelectedFeed()
                    } else {
                        isShowingAccessGate = true
                    }
                }
            }
            .onChange(of: settingsStore.feedConfigURL) { _ in
                configureTranscriptPolling()
                configureIncidentPolling()
                Task {
                    await catalogStore.loadCountries(feedConfigURL: settingsStore.trimmedFeedConfigURL)
                    await monetizationStore.refreshEntitlements(feedConfigURL: settingsStore.trimmedFeedConfigURL)
                    await rewardedAdStore.preload(
                        adUnitID: AppConfig.adMobRewardedAdUnitID,
                        customData: rewardCustomData
                    )
                }
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

            Text(selectedFeed?.name ?? "Choose a feed or use the default Phillipsburg / Easton feed")
                .font(.headline)
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)

            Text(AppConfig.subtitle)
                .font(.subheadline)
                .foregroundStyle(.secondary)

            Label(monetizationStore.statusText, systemImage: monetizationStore.isPremium ? "checkmark.seal.fill" : "play.rectangle")
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
                        handlePlayTapped()
                    } label: {
                        Label(playButtonTitle, systemImage: playButtonIcon)
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)

                    Button {
                        Task { await startPlaybackForSelectedFeed(forceRefresh: true) }
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

    private var catalogSection: some View {
        panel {
            VStack(alignment: .leading, spacing: 12) {
                sectionTitle("Browse Scanner Feeds", systemImage: "globe.americas.fill")

                HStack(spacing: 8) {
                    TextField("Search feeds", text: $catalogStore.searchText)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .textFieldStyle(.roundedBorder)

                    Button {
                        Task { await catalogStore.search(feedConfigURL: settingsStore.trimmedFeedConfigURL) }
                    } label: {
                        Image(systemName: "magnifyingglass")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(catalogStore.searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .accessibilityLabel("Search feeds")
                }

                HStack(spacing: 8) {
                    catalogMenu(
                        title: catalogStore.selectedCountry?.name ?? "Country",
                        systemImage: "globe",
                        items: catalogStore.countries
                    ) { item in
                        Task { await catalogStore.chooseCountry(item, feedConfigURL: settingsStore.trimmedFeedConfigURL) }
                    }

                    catalogMenu(
                        title: catalogStore.selectedState?.name ?? "State",
                        systemImage: "map",
                        items: catalogStore.states
                    ) { item in
                        Task { await catalogStore.chooseState(item, feedConfigURL: settingsStore.trimmedFeedConfigURL) }
                    }

                    catalogMenu(
                        title: catalogStore.selectedCounty?.name ?? "County",
                        systemImage: "mappin.and.ellipse",
                        items: catalogStore.counties
                    ) { item in
                        Task { await catalogStore.chooseCounty(item, feedConfigURL: settingsStore.trimmedFeedConfigURL) }
                    }
                }
                .lineLimit(1)
                .minimumScaleFactor(0.75)

                if catalogStore.isLoading {
                    HStack(spacing: 8) {
                        ProgressView()
                        Text("Loading scanner catalog...")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }

                if let error = catalogStore.lastError {
                    Text("Catalog backend not reachable: \(error)")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                if catalogStore.feeds.isEmpty {
                    Text("Select a country, state, and county to list available feeds.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(catalogStore.feeds.prefix(30)) { feed in
                        feedRow(feed)

                        if feed.id != catalogStore.feeds.prefix(30).last?.id {
                            Divider()
                        }
                    }
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
                sectionTitle("Recent Incidents", systemImage: "text.bubble")

                if let pipeline = transcriptStore.pipelineStatus {
                    pipelineStatusRow(pipeline)
                }

                if let error = transcriptStore.lastError, settingsStore.enableTranscriptPolling {
                    Text("Transcript backend not reachable: \(error)")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                if transcriptStore.incidents.isEmpty && transcriptStore.events.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("No completed call transcripts yet.")
                            .font(.body)
                        Text(emptyTranscriptHint)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                } else if !transcriptStore.incidents.isEmpty {
                    ForEach(transcriptStore.incidents) { incident in
                        incidentTranscriptCard(incident)

                        if incident.id != transcriptStore.incidents.last?.id {
                            Divider()
                        }
                    }
                } else {
                    ForEach(transcriptStore.events) { event in
                        transcriptRow(event)

                        if event.id != transcriptStore.events.last?.id {
                            Divider()
                        }
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

    private func catalogMenu(
        title: String,
        systemImage: String,
        items: [CatalogItem],
        select: @escaping (CatalogItem) -> Void
    ) -> some View {
        Menu {
            if items.isEmpty {
                Text("No items loaded")
            } else {
                ForEach(items.prefix(150)) { item in
                    Button(item.name) {
                        select(item)
                    }
                }
            }
        } label: {
            Label(title, systemImage: systemImage)
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.bordered)
        .disabled(items.isEmpty)
    }

    private func feedRow(_ feed: CatalogItem) -> some View {
        Button {
            selectedFeed = feed
            radioPlayer.stop()
            monetizationStore.clearPlaySession()
            logStore.info("Selected feed \(feed.name) id=\(feed.resolvedFeedId)")
        } label: {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: selectedFeed?.resolvedFeedId == feed.resolvedFeedId ? "checkmark.circle.fill" : "dot.radiowaves.left.and.right")
                    .foregroundStyle(selectedFeed?.resolvedFeedId == feed.resolvedFeedId ? .green : .secondary)
                    .frame(width: 20)

                VStack(alignment: .leading, spacing: 4) {
                    Text(feed.name)
                        .font(.body)
                        .foregroundStyle(.primary)
                        .fixedSize(horizontal: false, vertical: true)

                    if !feed.displaySubtitle.isEmpty {
                        Text(feed.displaySubtitle)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    HStack(spacing: 10) {
                        if let listeners = feed.listeners {
                            Label("\(listeners)", systemImage: "person.2")
                        }
                        if let bitrate = feed.bitrate {
                            Label("\(bitrate) kbps", systemImage: "waveform")
                        }
                        Text("ID \(feed.resolvedFeedId)")
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .buttonStyle(.plain)
        .padding(.vertical, 4)
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

    private var emptyTranscriptHint: String {
        if transcriptStore.pipelineStatus?.hasOpenAIKey == false {
            return "The Pi can record calls, but OPENAI_API_KEY is not configured in the image yet."
        }

        return "The Pi records finished scanner chunks first, skips silence, then posts the most likely transcript here."
    }

    private var accessGateSheet: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 16) {
                Text(selectedFeed?.name ?? AppConfig.feedTitle)
                    .font(.title2)
                    .fontWeight(.semibold)
                    .fixedSize(horizontal: false, vertical: true)

                Text("Subscribe or watch a rewarded ad before playback.")
                    .font(.body)
                    .foregroundStyle(.secondary)

                Button {
                    Task {
                        let watchedAd = await rewardedAdStore.show(
                            adUnitID: AppConfig.adMobRewardedAdUnitID,
                            customData: rewardCustomData
                        )
                        let canUseDebugFallback = AppConfig.adMobRewardedAdUnitID.isEmpty
                        guard watchedAd || canUseDebugFallback else {
                            return
                        }

                        let granted = await monetizationStore.requestRewardedPlay(
                            feedConfigURL: settingsStore.trimmedFeedConfigURL,
                            feedId: selectedFeed?.resolvedFeedId
                        )
                        if granted {
                            isShowingAccessGate = false
                            await startPlaybackForSelectedFeed()
                        }
                    }
                } label: {
                    Label("Watch Ad to Play", systemImage: "play.rectangle.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(monetizationStore.isWorking)

                Button {
                    Task {
                        await monetizationStore.purchasePremium(feedConfigURL: settingsStore.trimmedFeedConfigURL)
                        if monetizationStore.isPremium {
                            isShowingAccessGate = false
                            await startPlaybackForSelectedFeed()
                        }
                    }
                } label: {
                    Label("Subscribe", systemImage: "checkmark.seal.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .disabled(monetizationStore.isWorking)

                if monetizationStore.isWorking {
                    ProgressView()
                }

                if let error = rewardedAdStore.lastError ?? monetizationStore.lastError {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer()
            }
            .padding(20)
            .navigationTitle("Playback Access")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        isShowingAccessGate = false
                    }
                }
            }
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

                if let duration = event.durationSeconds {
                    Text("\(Int(duration))s")
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

    private func incidentTranscriptCard(_ incident: IncidentSummary) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(incident.title ?? "Scanner Incident")
                        .font(.headline)
                        .fixedSize(horizontal: false, vertical: true)

                    Text(incident.updatedAt ?? "No update time")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer(minLength: 8)

                if let count = incident.transcriptCount {
                    Text("\(count) calls")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let summary = incident.summary, !summary.isEmpty {
                Text(summary)
                    .font(.body)
                    .fixedSize(horizontal: false, vertical: true)
            }

            ForEach(events(for: incident).prefix(3)) { event in
                VStack(alignment: .leading, spacing: 4) {
                    Text(event.timestamp)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(event.text)
                        .font(.footnote)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.top, 2)
            }

            if !incident.keywords.isEmpty {
                Text(incident.keywords.prefix(8).joined(separator: " | "))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }

    private func events(for incident: IncidentSummary) -> [TranscriptEvent] {
        transcriptStore.events.filter { $0.incidentId == incident.id }
    }

    private func pipelineStatusRow(_ pipeline: TranscriptPipelineStatus) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: pipeline.ok == false ? "exclamationmark.triangle.fill" : "waveform")
                .foregroundStyle(pipeline.ok == false ? .orange : .secondary)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 2) {
                Text(pipeline.state ?? "Transcript pipeline")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(pipeline.message ?? "Waiting for completed scanner audio.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
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

    private func handlePlayTapped() {
        if radioPlayer.isPlaying || radioPlayer.isLoading {
            radioPlayer.stop()
            return
        }

        if monetizationStore.canPlay {
            Task { await startPlaybackForSelectedFeed() }
        } else {
            isShowingAccessGate = true
        }
    }

    private func startPlaybackForSelectedFeed(forceRefresh: Bool = false) async {
        if monetizationStore.playToken == nil {
            let granted = await monetizationStore.requestRewardedPlay(
                feedConfigURL: settingsStore.trimmedFeedConfigURL,
                feedId: selectedFeed?.resolvedFeedId
            )
            guard granted else {
                isShowingAccessGate = true
                return
            }
        }

        if forceRefresh {
            await radioPlayer.refreshAndRetry(
                using: settingsStore.playerSettings,
                feed: selectedFeed,
                playToken: monetizationStore.playToken
            )
        } else {
            await radioPlayer.start(
                using: settingsStore.playerSettings,
                feed: selectedFeed,
                playToken: monetizationStore.playToken
            )
        }
    }

    private var rewardCustomData: String {
        [
            monetizationStore.appAccountToken.uuidString,
            selectedFeed?.resolvedFeedId ?? AppConfig.feedTitle
        ].joined(separator: "|")
    }
}

#Preview {
    ContentView()
}

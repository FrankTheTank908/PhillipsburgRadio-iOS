import Foundation
import AVFoundation
import Combine

@MainActor
final class RadioPlayer: ObservableObject {
    @Published private(set) var isPlaying = false
    @Published private(set) var isLoading = false
    @Published var statusText = "Stopped"
    @Published var currentStreamURL: String = ""
    @Published var lastUpdated: String = "Not loaded yet"
    @Published var expiresAt: String = "Not provided"
    @Published var source: String = "Not loaded yet"
    @Published var feedId: String = "Not loaded yet"
    @Published var apiStatus: String = "Not loaded yet"
    @Published var listenerCount: String = "Not loaded yet"
    @Published var bitrate: String = "Not loaded yet"
    @Published var errorMessage: String?

    private let feedService = FeedURLService()
    private var player: AVPlayer?
    private var statusObserver: NSKeyValueObservation?
    private var timeControlObserver: NSKeyValueObservation?
    private var notificationTokens: [NSObjectProtocol] = []
    private var retryTask: Task<Void, Never>?
    private var stallRecoveryTask: Task<Void, Never>?
    private var wantsPlayback = false
    private var retryCount = 0
    private var activeRequestID: UUID?
    private var logger: AppLogStore?
    private var currentSettings: PlayerSettingsSnapshot = .default
    private var currentFeed: CatalogItem?

    func attachLogger(_ logger: AppLogStore) {
        self.logger = logger
    }

    func playOrStop(using settings: PlayerSettingsSnapshot, feed: CatalogItem? = nil) {
        if wantsPlayback || isLoading {
            stop()
        } else {
            Task { await start(using: settings, feed: feed) }
        }
    }

    func start(using settings: PlayerSettingsSnapshot, feed: CatalogItem? = nil) async {
        await startPlayback(resetRetryCount: true, settings: settings, feed: feed)
    }

    func refreshAndRetry(using settings: PlayerSettingsSnapshot, feed: CatalogItem? = nil) async {
        await startPlayback(resetRetryCount: true, settings: settings, feed: feed)
    }

    func stop() {
        logInfo("Playback stopped")
        wantsPlayback = false
        activeRequestID = nil
        retryTask?.cancel()
        retryTask = nil
        stallRecoveryTask?.cancel()
        stallRecoveryTask = nil
        clearPlayer()
        isPlaying = false
        isLoading = false
        statusText = "Stopped"
    }

    private func startPlayback(resetRetryCount: Bool, settings: PlayerSettingsSnapshot, feed: CatalogItem? = nil) async {
        currentSettings = settings
        if let feed {
            currentFeed = feed
        }
        retryTask?.cancel()
        retryTask = nil
        stallRecoveryTask?.cancel()
        stallRecoveryTask = nil

        if resetRetryCount {
            retryCount = 0
        }

        let requestID = UUID()
        activeRequestID = requestID
        wantsPlayback = true
        clearPlayer()
        errorMessage = nil
        isLoading = true
        statusText = retryCount == 0 ? "Fetching live feed URL..." : "Retrying with fresh stream URL..."
        logInfo("Fetching feed config from \(settings.feedConfigURL)")

        do {
            let shouldForceRefresh = retryCount > 0 || (resetRetryCount && !currentStreamURL.isEmpty)
            let config = try await feedService.fetchCurrentConfig(
                feedConfigURL: settings.feedConfigURL,
                feedId: feed?.resolvedFeedId,
                forceRefresh: shouldForceRefresh
            )

            guard wantsPlayback, activeRequestID == requestID else {
                return
            }

            guard let url = URL(string: config.streamUrl) else {
                throw FeedURLError.invalidStreamURL
            }

            currentStreamURL = config.streamUrl
            lastUpdated = config.updatedAt ?? "No update time provided"
            expiresAt = config.expiresAt ?? "Not provided"
            source = config.source ?? "Unknown source"
            feedId = config.feedId ?? feed?.name ?? "Selected Feed"
            apiStatus = config.status ?? "Unknown"
            listenerCount = config.listeners.map { String($0) } ?? "Unknown"
            bitrate = config.bitrate.map { "\($0) kbps" } ?? "Unknown"
            logInfo("Loaded feed config source=\(source), status=\(apiStatus), listeners=\(listenerCount)")

            statusText = "Connecting to live audio..."
            let item = AVPlayerItem(url: url)
            let newPlayer = AVPlayer(playerItem: item)
            player = newPlayer

            observe(player: newPlayer, item: item)

            newPlayer.play()
            isPlaying = true
            isLoading = false
            statusText = "Playing live audio"
            logInfo("Started AVPlayer")
        } catch {
            guard activeRequestID == requestID else {
                return
            }

            isLoading = false
            isPlaying = false
            statusText = "Failed to play"
            errorMessage = error.localizedDescription
            wantsPlayback = false
            logError("Playback start failed: \(error.localizedDescription)")
        }
    }

    private func clearPlayer() {
        statusObserver?.invalidate()
        timeControlObserver?.invalidate()
        statusObserver = nil
        timeControlObserver = nil
        notificationTokens.forEach { NotificationCenter.default.removeObserver($0) }
        notificationTokens.removeAll()
        player?.pause()
        player = nil
    }

    private func observe(player: AVPlayer, item: AVPlayerItem) {
        let notificationCenter = NotificationCenter.default

        notificationTokens = [
            notificationCenter.addObserver(
                forName: .AVPlayerItemFailedToPlayToEndTime,
                object: item,
                queue: .main
            ) { [weak self] notification in
                let error = notification.userInfo?[AVPlayerItemFailedToPlayToEndTimeErrorKey] as? Error
                Task { @MainActor in
                    self?.handlePlaybackIssue(error?.localizedDescription ?? "The stream failed before playback ended.")
                }
            },
            notificationCenter.addObserver(
                forName: .AVPlayerItemPlaybackStalled,
                object: item,
                queue: .main
            ) { [weak self] _ in
                Task { @MainActor in
                    self?.scheduleStallRecovery()
                }
            }
        ]

        statusObserver = item.observe(\.status, options: [.new, .initial]) { [weak self] item, _ in
            Task { @MainActor in
                guard let self else { return }
                switch item.status {
                case .failed:
                    self.handlePlaybackIssue(item.error?.localizedDescription ?? "The stream failed. Fetching a new URL may fix it.")
                case .readyToPlay:
                    if self.isPlaying {
                        self.statusText = "Playing live audio"
                    }
                case .unknown:
                    break
                @unknown default:
                    break
                }
            }
        }

        timeControlObserver = player.observe(\.timeControlStatus, options: [.new]) { [weak self] player, _ in
            Task { @MainActor in
                guard let self else { return }
                switch player.timeControlStatus {
                case .waitingToPlayAtSpecifiedRate:
                    if self.isPlaying {
                        self.statusText = "Buffering..."
                        self.scheduleStallRecovery()
                    }
                case .playing:
                    self.stallRecoveryTask?.cancel()
                    self.stallRecoveryTask = nil
                    self.statusText = "Playing live audio"
                case .paused:
                    if self.isPlaying { self.statusText = "Paused" }
                @unknown default:
                    break
                }
            }
        }
    }

    private func scheduleStallRecovery() {
        guard wantsPlayback, stallRecoveryTask == nil else { return }

        stallRecoveryTask = Task { [weak self] in
            let seconds = await MainActor.run { self?.currentSettings.stallRecoverySeconds ?? AppConfig.stallRecoverySeconds }
            do {
                try await Task.sleep(nanoseconds: UInt64(seconds) * 1_000_000_000)
            } catch {
                return
            }

            guard !Task.isCancelled else { return }

            await MainActor.run {
                guard
                    let self,
                    self.wantsPlayback,
                    self.player?.timeControlStatus == .waitingToPlayAtSpecifiedRate
                else { return }

                self.handlePlaybackIssue("The stream stalled. Fetching a fresh URL...")
            }
        }
    }

    private func handlePlaybackIssue(_ message: String) {
        guard wantsPlayback else { return }
        guard retryTask == nil else { return }

        stallRecoveryTask?.cancel()
        stallRecoveryTask = nil
        clearPlayer()
        isPlaying = false
        isLoading = false
        errorMessage = message
        logWarning(message)

        guard retryCount < currentSettings.automaticRetryLimit else {
            wantsPlayback = false
            statusText = "Playback failed"
            errorMessage = "\(message) Tap Refresh URL to try again."
            logError("Retry limit reached")
            return
        }

        retryCount += 1
        statusText = "Stream interrupted. Refreshing URL..."
        logInfo("Retry \(retryCount) scheduled")
        retryTask?.cancel()
        let retrySettings = currentSettings
        let retryFeed = currentFeed
        retryTask = Task { [weak self] in
            do {
                try await Task.sleep(nanoseconds: 1_500_000_000)
            } catch {
                return
            }

            guard !Task.isCancelled else { return }

            await self?.startPlayback(resetRetryCount: false, settings: retrySettings, feed: retryFeed)
        }
    }

    private func logInfo(_ message: String) {
        guard currentSettings.enableVerboseLogs else { return }
        logger?.info(message)
    }

    private func logWarning(_ message: String) {
        logger?.warning(message)
    }

    private func logError(_ message: String) {
        logger?.error(message)
    }
}

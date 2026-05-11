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
    @Published var errorMessage: String?

    private let feedService = FeedURLService()
    private var player: AVPlayer?
    private var statusObserver: NSKeyValueObservation?
    private var timeControlObserver: NSKeyValueObservation?

    func playOrStop() {
        if isPlaying || isLoading {
            stop()
        } else {
            Task { await start() }
        }
    }

    func start() async {
        stop()
        errorMessage = nil
        isLoading = true
        statusText = "Fetching live feed URL..."

        do {
            let config = try await feedService.fetchCurrentConfig()
            guard let url = URL(string: config.streamUrl) else {
                throw FeedURLError.invalidStreamURL
            }

            currentStreamURL = config.streamUrl
            lastUpdated = config.updatedAt ?? "No update time provided"

            statusText = "Connecting to live audio..."
            let item = AVPlayerItem(url: url)
            let newPlayer = AVPlayer(playerItem: item)
            player = newPlayer

            observe(player: newPlayer, item: item)

            newPlayer.play()
            isPlaying = true
            isLoading = false
            statusText = "Playing live audio"
        } catch {
            isLoading = false
            isPlaying = false
            statusText = "Failed to play"
            errorMessage = error.localizedDescription
        }
    }

    func refreshAndRetry() async {
        stop()
        await start()
    }

    func stop() {
        statusObserver?.invalidate()
        timeControlObserver?.invalidate()
        statusObserver = nil
        timeControlObserver = nil
        player?.pause()
        player = nil
        isPlaying = false
        isLoading = false
        statusText = "Stopped"
    }

    private func observe(player: AVPlayer, item: AVPlayerItem) {
        statusObserver = item.observe(\.status, options: [.new, .initial]) { [weak self] item, _ in
            Task { @MainActor in
                guard let self else { return }
                switch item.status {
                case .failed:
                    self.isPlaying = false
                    self.isLoading = false
                    self.statusText = "Playback failed"
                    self.errorMessage = item.error?.localizedDescription ?? "The stream failed. Tap Refresh to fetch a new URL."
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
                    if self.isPlaying { self.statusText = "Buffering..." }
                case .playing:
                    self.statusText = "Playing live audio"
                case .paused:
                    if self.isPlaying { self.statusText = "Paused" }
                @unknown default:
                    break
                }
            }
        }
    }
}

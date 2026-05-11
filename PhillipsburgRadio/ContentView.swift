import SwiftUI

struct ContentView: View {
    @StateObject private var radioPlayer = RadioPlayer()

    private let sampleTranscripts: [TranscriptEvent] = [
        TranscriptEvent(time: "--:--", text: "Live transcript placeholder. Firebase/Supabase transcript feed will be connected later."),
        TranscriptEvent(time: "--:--", text: "Audio player is ready to use once AppConfig.feedConfigURL points to your JSON file."),
        TranscriptEvent(time: "--:--", text: "If the Broadcastify .mp3 changes or expires, tap Refresh Stream URL.")
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    headerCard
                    playerCard
                    streamInfoCard
                    transcriptCard
                }
                .padding()
            }
            .navigationTitle(AppConfig.appTitle)
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private var headerCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(AppConfig.feedTitle)
                .font(.title2)
                .fontWeight(.bold)

            Text(AppConfig.subtitle)
                .font(.subheadline)
                .foregroundStyle(.secondary)

            Label("Live feed", systemImage: "dot.radiowaves.left.and.right")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private var playerCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Audio Player")
                .font(.headline)

            HStack(spacing: 14) {
                Button {
                    radioPlayer.playOrStop()
                } label: {
                    Label(radioPlayer.isPlaying || radioPlayer.isLoading ? "Stop" : "Play", systemImage: radioPlayer.isPlaying || radioPlayer.isLoading ? "stop.fill" : "play.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)

                Button {
                    Task { await radioPlayer.refreshAndRetry() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            }

            HStack {
                ProgressView()
                    .opacity(radioPlayer.isLoading ? 1 : 0)
                Text(radioPlayer.statusText)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            if let error = radioPlayer.errorMessage {
                Text(error)
                    .font(.footnote)
                    .foregroundStyle(.red)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private var streamInfoCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Current Stream Config")
                .font(.headline)

            Text("Last updated: \(radioPlayer.lastUpdated)")
                .font(.footnote)
                .foregroundStyle(.secondary)

            Text(radioPlayer.currentStreamURL.isEmpty ? "No stream URL loaded yet." : radioPlayer.currentStreamURL)
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private var transcriptCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Live Transcript")
                .font(.headline)

            ForEach(sampleTranscripts) { event in
                VStack(alignment: .leading, spacing: 4) {
                    Text(event.time)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(event.text)
                        .font(.body)
                }
                .padding(.vertical, 6)

                Divider()
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.thinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

#Preview {
    ContentView()
}

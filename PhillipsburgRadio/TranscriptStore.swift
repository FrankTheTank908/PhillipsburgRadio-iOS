import Foundation
import Combine

@MainActor
final class TranscriptStore: ObservableObject {
    @Published private(set) var events: [TranscriptEvent] = []
    @Published private(set) var incidents: [IncidentSummary] = []
    @Published private(set) var pipelineStatus: TranscriptPipelineStatus?
    @Published private(set) var lastError: String?

    private var pollingTask: Task<Void, Never>?
    private var logger: AppLogStore?

    func attachLogger(_ logger: AppLogStore) {
        self.logger = logger
    }

    func startPolling(feedConfigURL: String) {
        stopPolling()

        guard let transcriptsURL = makeTranscriptsURL(from: feedConfigURL) else {
            lastError = "Transcript URL could not be built."
            logger?.warning(lastError ?? "Transcript URL error")
            return
        }

        pollingTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.fetchOnce(url: transcriptsURL)

                do {
                    try await Task.sleep(nanoseconds: 10_000_000_000)
                } catch {
                    return
                }
            }
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }

    private func fetchOnce(url: URL) async {
        do {
            var request = URLRequest(url: url)
            request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
            request.timeoutInterval = 8
            request.setValue("application/json", forHTTPHeaderField: "Accept")

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                throw URLError(.badServerResponse)
            }

            let decoded = try JSONDecoder().decode(TranscriptResponse.self, from: data)
            events = decoded.events
            incidents = decoded.incidents ?? []
            pipelineStatus = decoded.pipeline
            lastError = nil
        } catch {
            lastError = error.localizedDescription
        }
    }

    private func makeTranscriptsURL(from feedConfigURL: String) -> URL? {
        guard
            let url = URL(string: feedConfigURL),
            var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        else {
            return nil
        }

        components.path = "/transcripts"
        components.queryItems = [
            URLQueryItem(name: "limit", value: "75"),
            URLQueryItem(name: "incidentLimit", value: "25")
        ]
        return components.url
    }
}

import Foundation
import Combine

@MainActor
final class IncidentStore: ObservableObject {
    @Published private(set) var messages: [IncidentMessage] = []
    @Published private(set) var lastError: String?
    @Published private(set) var isSending = false

    private var pollingTask: Task<Void, Never>?
    private var logger: AppLogStore?

    func attachLogger(_ logger: AppLogStore) {
        self.logger = logger
    }

    func startPolling(feedConfigURL: String) {
        stopPolling()

        guard let incidentsURL = makeIncidentsURL(from: feedConfigURL) else {
            lastError = "Incident chat URL could not be built."
            logger?.warning(lastError ?? "Incident chat URL error")
            return
        }

        pollingTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.fetchOnce(url: incidentsURL)

                do {
                    try await Task.sleep(nanoseconds: 8_000_000_000)
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

    func send(text: String, feedConfigURL: String) async -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return false
        }

        guard let incidentsURL = makeIncidentsURL(from: feedConfigURL) else {
            lastError = "Incident chat URL could not be built."
            logger?.warning(lastError ?? "Incident chat URL error")
            return false
        }

        isSending = true
        defer { isSending = false }

        do {
            var request = URLRequest(url: incidentsURL)
            request.httpMethod = "POST"
            request.timeoutInterval = 8
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.httpBody = try JSONSerialization.data(
                withJSONObject: [
                    "author": "Frank",
                    "text": trimmed,
                    "channel": "Incident Chat"
                ],
                options: []
            )

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
                throw URLError(.badServerResponse)
            }

            let decoded = try JSONDecoder().decode(SendIncidentResponse.self, from: data)
            messages.append(decoded.message)
            lastError = nil
            logger?.info("Incident message posted")
            return true
        } catch {
            lastError = error.localizedDescription
            logger?.warning("Incident message failed: \(error.localizedDescription)")
            return false
        }
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

            let decoded = try JSONDecoder().decode(IncidentResponse.self, from: data)
            messages = decoded.messages
            lastError = nil
        } catch {
            lastError = error.localizedDescription
        }
    }

    private func makeIncidentsURL(from feedConfigURL: String) -> URL? {
        guard
            let url = URL(string: feedConfigURL),
            var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        else {
            return nil
        }

        components.path = "/incidents"
        components.queryItems = [URLQueryItem(name: "limit", value: "50")]
        return components.url
    }

    private struct SendIncidentResponse: Codable {
        let message: IncidentMessage
    }
}

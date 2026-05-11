import Foundation

enum FeedURLError: LocalizedError {
    case missingConfigURL
    case invalidConfigURL
    case invalidStreamURL
    case badServerResponse

    var errorDescription: String? {
        switch self {
        case .missingConfigURL:
            return "The feed config URL is missing."
        case .invalidConfigURL:
            return "The feed config URL is invalid."
        case .invalidStreamURL:
            return "The stream URL from the config file is invalid."
        case .badServerResponse:
            return "The server returned an invalid response."
        }
    }
}

final class FeedURLService {
    func fetchCurrentConfig() async throws -> FeedConfig {
        guard !AppConfig.feedConfigURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw FeedURLError.missingConfigURL
        }

        guard let url = URL(string: AppConfig.feedConfigURL) else {
            throw FeedURLError.invalidConfigURL
        }

        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.timeoutInterval = 12
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw FeedURLError.badServerResponse
        }

        return try JSONDecoder().decode(FeedConfig.self, from: data)
    }

    func fetchCurrentStreamURL() async throws -> URL {
        let config = try await fetchCurrentConfig()

        guard let streamURL = URL(string: config.streamUrl) else {
            throw FeedURLError.invalidStreamURL
        }

        return streamURL
    }
}

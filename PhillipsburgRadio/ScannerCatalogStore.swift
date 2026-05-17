import Foundation
import Combine

@MainActor
final class ScannerCatalogStore: ObservableObject {
    @Published private(set) var countries: [CatalogItem] = []
    @Published private(set) var states: [CatalogItem] = []
    @Published private(set) var counties: [CatalogItem] = []
    @Published private(set) var feeds: [CatalogItem] = []
    @Published private(set) var isLoading = false
    @Published private(set) var lastError: String?
    @Published var selectedCountry: CatalogItem?
    @Published var selectedState: CatalogItem?
    @Published var selectedCounty: CatalogItem?
    @Published var searchText = ""

    private let feedService = FeedURLService()
    private var logger: AppLogStore?

    func attachLogger(_ logger: AppLogStore) {
        self.logger = logger
    }

    func loadCountries(feedConfigURL: String) async {
        await load(feedConfigURL: feedConfigURL, path: "/catalog/countries", queryItems: []) { [weak self] items in
            self?.countries = items
        }
    }

    func chooseCountry(_ country: CatalogItem, feedConfigURL: String) async {
        selectedCountry = country
        selectedState = nil
        selectedCounty = nil
        states = []
        counties = []
        feeds = []

        await load(
            feedConfigURL: feedConfigURL,
            path: "/catalog/states",
            queryItems: [URLQueryItem(name: "coid", value: country.id)]
        ) { [weak self] items in
            self?.states = items
        }
    }

    func chooseState(_ state: CatalogItem, feedConfigURL: String) async {
        selectedState = state
        selectedCounty = nil
        counties = []
        feeds = []

        await load(
            feedConfigURL: feedConfigURL,
            path: "/catalog/counties",
            queryItems: [URLQueryItem(name: "stid", value: state.id)]
        ) { [weak self] items in
            self?.counties = items
        }
    }

    func chooseCounty(_ county: CatalogItem, feedConfigURL: String) async {
        selectedCounty = county
        feeds = []

        await load(
            feedConfigURL: feedConfigURL,
            path: "/catalog/feeds",
            queryItems: [URLQueryItem(name: "ctid", value: county.id)]
        ) { [weak self] items in
            self?.feeds = items
        }
    }

    func search(feedConfigURL: String) async {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return }

        await load(
            feedConfigURL: feedConfigURL,
            path: "/catalog/feeds",
            queryItems: [URLQueryItem(name: "s", value: query)]
        ) { [weak self] items in
            self?.feeds = items
        }
    }

    private func load(
        feedConfigURL: String,
        path: String,
        queryItems: [URLQueryItem],
        assign: @escaping ([CatalogItem]) -> Void
    ) async {
        isLoading = true
        lastError = nil
        defer { isLoading = false }

        do {
            let response = try await feedService.fetchCatalog(
                feedConfigURL: feedConfigURL,
                path: path,
                queryItems: queryItems
            )
            assign(response.items)
            logger?.info("Catalog loaded path=\(path) count=\(response.items.count)")
        } catch {
            lastError = error.localizedDescription
            logger?.warning("Catalog load failed: \(error.localizedDescription)")
        }
    }
}

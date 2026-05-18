import Foundation
import Combine

@MainActor
final class FavoritesStore: ObservableObject {
    @Published private(set) var feeds: [CatalogItem] = []

    private let defaults: UserDefaults
    private let key = "favorites.feeds"

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        load()
    }

    func contains(_ feed: CatalogItem) -> Bool {
        feeds.contains { $0.resolvedFeedId == feed.resolvedFeedId }
    }

    func toggle(_ feed: CatalogItem) {
        if contains(feed) {
            remove(feed)
        } else {
            add(feed)
        }
    }

    func add(_ feed: CatalogItem) {
        guard !contains(feed) else { return }
        feeds.insert(feed, at: 0)
        save()
    }

    func remove(_ feed: CatalogItem) {
        feeds.removeAll { $0.resolvedFeedId == feed.resolvedFeedId }
        save()
    }

    private func load() {
        guard let data = defaults.data(forKey: key) else {
            feeds = []
            return
        }

        do {
            feeds = try JSONDecoder().decode([CatalogItem].self, from: data)
        } catch {
            feeds = []
        }
    }

    private func save() {
        do {
            let data = try JSONEncoder().encode(feeds)
            defaults.set(data, forKey: key)
        } catch {
            defaults.removeObject(forKey: key)
        }
    }
}

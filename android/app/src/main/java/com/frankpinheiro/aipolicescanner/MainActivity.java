package com.frankpinheiro.aipolicescanner;

import android.app.Activity;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final String PREFS = "ai_police_scanner";
    private static final String FAVORITES = "favorites";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private FrameLayout content;
    private SharedPreferences preferences;
    private String currentFeedId = "45951";
    private String currentFeedName = "Default Scanner Feed";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        setContentView(rootView());
        showFeed();
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

    private View rootView() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(246, 248, 251));

        content = new FrameLayout(this);
        root.addView(content, new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            0,
            1f
        ));

        LinearLayout nav = new LinearLayout(this);
        nav.setOrientation(LinearLayout.HORIZONTAL);
        nav.setGravity(Gravity.CENTER);
        nav.setPadding(8, 8, 8, 8);
        nav.setBackgroundColor(Color.WHITE);
        root.addView(nav, new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ));

        nav.addView(navButton("Feed", this::showFeed), navParams());
        nav.addView(navButton("Favorites", this::showFavorites), navParams());
        nav.addView(navButton("Settings", this::showSettings), navParams());
        return root;
    }

    private LinearLayout.LayoutParams navParams() {
        return new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
    }

    private Button navButton(String title, Runnable action) {
        Button button = new Button(this);
        button.setText(title);
        button.setAllCaps(false);
        button.setOnClickListener(view -> action.run());
        return button;
    }

    private void showFeed() {
        LinearLayout page = page();
        page.addView(title("AI Police Scanner"));
        page.addView(subtitle(currentFeedName));
        page.addView(primaryButton("Refresh Feed", this::loadCurrentFeed));
        page.addView(primaryButton("Favorite Feed", () -> {
            saveFavorite(currentFeedId + "|" + currentFeedName);
            showFavorites();
        }));
        page.addView(section("Browse", "Worldwide country/state/county browsing will use the same Pi catalog API as the iOS app."));
        page.addView(section("Incidents", "AI transcripts and incident summaries come from the Pi after completed calls and archives are processed."));
        swap(page);
    }

    private void showFavorites() {
        LinearLayout page = page();
        page.addView(title("Favorites"));
        List<String> favorites = new ArrayList<>(favorites());
        if (favorites.isEmpty()) {
            page.addView(section("Saved Feeds", "No favorites saved yet."));
        } else {
            for (String favorite : favorites) {
                String[] parts = favorite.split("\\|", 2);
                String feedId = parts.length > 0 ? parts[0] : "";
                String name = parts.length > 1 ? parts[1] : feedId;
                Button row = secondaryButton(name, () -> {
                    currentFeedId = feedId;
                    currentFeedName = name;
                    showFeed();
                });
                page.addView(row);
            }
        }
        swap(page);
    }

    private void showSettings() {
        LinearLayout page = page();
        page.addView(title("Settings"));
        page.addView(section("Backend", BuildConfig.APP_FEED_CONFIG_URL));
        page.addView(section("Build", "Unsigned debug APK from GitHub Actions."));
        swap(page);
    }

    private LinearLayout page() {
        LinearLayout page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL);
        page.setPadding(24, 24, 24, 24);
        return page;
    }

    private TextView title(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextColor(Color.rgb(17, 24, 39));
        view.setTextSize(30);
        view.setGravity(Gravity.START);
        view.setPadding(0, 0, 0, 6);
        return view;
    }

    private TextView subtitle(String text) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextColor(Color.rgb(75, 85, 99));
        view.setTextSize(16);
        view.setPadding(0, 0, 0, 18);
        return view;
    }

    private TextView section(String heading, String body) {
        TextView view = new TextView(this);
        view.setText(heading + "\n" + body);
        view.setTextColor(Color.rgb(31, 41, 55));
        view.setTextSize(16);
        view.setPadding(0, 18, 0, 18);
        return view;
    }

    private Button primaryButton(String text, Runnable action) {
        Button button = secondaryButton(text, action);
        button.setTextColor(Color.WHITE);
        button.setBackgroundColor(Color.rgb(37, 99, 235));
        return button;
    }

    private Button secondaryButton(String text, Runnable action) {
        Button button = new Button(this);
        button.setText(text);
        button.setAllCaps(false);
        button.setOnClickListener(view -> action.run());
        return button;
    }

    private void swap(View view) {
        ScrollView scrollView = new ScrollView(this);
        scrollView.addView(view);
        content.removeAllViews();
        content.addView(scrollView);
    }

    private void loadCurrentFeed() {
        executor.execute(() -> {
            try {
                URL url = new URL(BuildConfig.APP_FEED_CONFIG_URL + "?feedId=" + currentFeedId);
                HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                connection.setRequestProperty("Accept", "application/json");
                connection.setConnectTimeout(10000);
                connection.setReadTimeout(10000);
                StringBuilder builder = new StringBuilder();
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(connection.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        builder.append(line);
                    }
                }
                String body = builder.toString();
                String title = extractJsonString(body, "title");
                if (!title.isEmpty()) {
                    currentFeedName = title;
                }
                runOnUiThread(this::showFeedSummary);
            } catch (Exception error) {
                runOnUiThread(() -> showMessage("Feed unavailable", error.getMessage()));
            }
        });
    }

    private void showFeedSummary() {
        showMessage("Feed Ready", currentFeedName);
    }

    private void showMessage(String heading, String body) {
        LinearLayout page = page();
        page.addView(title(heading));
        page.addView(subtitle(body == null ? "" : body));
        page.addView(primaryButton("Back to Feed", this::showFeed));
        swap(page);
    }

    private String extractJsonString(String body, String field) {
        String key = "\"" + field + "\"";
        int index = body.indexOf(key);
        if (index < 0) {
            return "";
        }
        int colon = body.indexOf(":", index);
        int start = body.indexOf("\"", colon + 1);
        int end = start < 0 ? -1 : body.indexOf("\"", start + 1);
        return start >= 0 && end > start ? body.substring(start + 1, end) : "";
    }

    private Set<String> favorites() {
        return new HashSet<>(preferences.getStringSet(FAVORITES, new HashSet<>()));
    }

    private void saveFavorite(String favorite) {
        Set<String> set = favorites();
        set.add(favorite);
        preferences.edit().putStringSet(FAVORITES, set).apply();
    }
}

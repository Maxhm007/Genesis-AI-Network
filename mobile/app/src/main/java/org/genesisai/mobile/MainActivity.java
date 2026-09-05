package org.genesisai.mobile;

import android.app.Activity;
import android.os.Bundle;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final String SNAPSHOT_FILE = "genesis_backup_state.json";
    private static final String LOCAL_PULSE_FILE = "genesis_local_pulse.json";
    private static final String RECONCILE_FILE = "genesis_reconcile_candidate.json";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private EditText baseUrl;
    private EditText token;
    private EditText message;
    private TextView status;
    private TextView reply;
    private TextView backupStatus;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(32, 32, 32, 32);
        scroll.addView(root);

        TextView title = new TextView(this);
        title.setText("Genesis AI");
        title.setTextSize(28f);
        root.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("Genesis mobile client + secondary backup body");
        subtitle.setPadding(0, 0, 0, 24);
        root.addView(subtitle);

        baseUrl = field("Genesis API URL (HTTPS)", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        baseUrl.setText(getPreferences(MODE_PRIVATE).getString("base_url", ""));
        root.addView(baseUrl);

        token = field("Bearer token (not stored)", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        root.addView(token);

        Button dashboardButton = new Button(this);
        dashboardButton.setText("Open Genesis Dashboard");
        dashboardButton.setOnClickListener(v -> showGenesisDashboard());
        root.addView(dashboardButton);

        Button healthButton = new Button(this);
        healthButton.setText("Check Genesis Status");
        healthButton.setOnClickListener(v -> checkHealth());
        root.addView(healthButton);

        status = new TextView(this);
        status.setText("Status: not connected");
        status.setPadding(0, 8, 0, 24);
        root.addView(status);

        TextView backupTitle = new TextView(this);
        backupTitle.setText("Phone Backup Body");
        backupTitle.setTextSize(20f);
        root.addView(backupTitle);

        backupStatus = new TextView(this);
        backupStatus.setPadding(0, 8, 0, 8);
        root.addView(backupStatus);
        refreshBackupStatus();

        Button armButton = new Button(this);
        armButton.setText("Arm / Disarm Backup Body");
        armButton.setOnClickListener(v -> toggleBackupBody());
        root.addView(armButton);

        Button syncButton = new Button(this);
        syncButton.setText("Sync Genesis State to Phone");
        syncButton.setOnClickListener(v -> syncBackupState());
        root.addView(syncButton);

        Button offlineButton = new Button(this);
        offlineButton.setText("View Offline Backup State");
        offlineButton.setOnClickListener(v -> viewOfflineBackup());
        root.addView(offlineButton);

        Button pulseButton = new Button(this);
        pulseButton.setText("Run One Local Emergency Pulse");
        pulseButton.setOnClickListener(v -> runLocalEmergencyPulse());
        root.addView(pulseButton);

        Button candidateButton = new Button(this);
        candidateButton.setText("View Pending Reconciliation Candidate");
        candidateButton.setOnClickListener(v -> viewPendingCandidate());
        root.addView(candidateButton);

        TextView backupNote = new TextView(this);
        backupNote.setText("Pulses remain Genesis's primary continuity. The phone only performs bounded emergency pulses while armed. Local results are candidate evidence and cannot mutate canonical Genesis until normal network validation accepts them.");
        backupNote.setPadding(0, 8, 0, 24);
        root.addView(backupNote);

        message = field("Message Genesis", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        message.setMinLines(4);
        root.addView(message);

        Button sendButton = new Button(this);
        sendButton.setText("Send");
        sendButton.setOnClickListener(v -> sendMessage());
        root.addView(sendButton);

        reply = new TextView(this);
        reply.setText("Genesis reply and dashboard will appear here.");
        reply.setPadding(0, 24, 0, 32);
        root.addView(reply);

        TextView security = new TextView(this);
        security.setText("Security: HTTPS-only remote access. Bearer token stays memory-only. Backup state, emergency-pulse state, and reconciliation candidates stay in app-private storage. Local emergency pulses cannot directly modify canonical Genesis code.");
        root.addView(security);

        setContentView(scroll);
    }

    private EditText field(String hint, int type) {
        EditText edit = new EditText(this);
        edit.setHint(hint);
        edit.setInputType(type);
        return edit;
    }

    private String normalizedBaseUrl() {
        String value = baseUrl.getText().toString().trim();
        while (value.endsWith("/")) value = value.substring(0, value.length() - 1);
        try {
            URI uri = new URI(value);
            boolean secureOrigin = "https".equalsIgnoreCase(uri.getScheme())
                    && uri.getHost() != null
                    && !uri.getHost().isBlank()
                    && uri.getUserInfo() == null
                    && uri.getQuery() == null
                    && uri.getFragment() == null;
            if (!secureOrigin) {
                throw new IllegalArgumentException("Use a credential-free HTTPS Genesis API origin");
            }
        } catch (java.net.URISyntaxException e) {
            throw new IllegalArgumentException("Use a valid HTTPS Genesis API origin", e);
        }
        getPreferences(MODE_PRIVATE).edit().putString("base_url", value).apply();
        return value;
    }

    private void showGenesisDashboard() {
        reply.setText("Loading Genesis dashboard…");
        executor.submit(() -> {
            boolean live = false;
            JSONObject snapshot;
            try {
                String body = request("GET", normalizedBaseUrl() + "/v1/owner/dashboard", null, true);
                snapshot = new JSONObject(body);
                snapshot.put("phone_backup_snapshot", true);
                snapshot.put("snapshot_epoch_ms", System.currentTimeMillis());
                writePrivateJson(SNAPSHOT_FILE, snapshot);
                live = true;
            } catch (Exception liveError) {
                try {
                    snapshot = readPrivateJson(SNAPSHOT_FILE);
                } catch (Exception offlineError) {
                    showError("Dashboard unavailable", liveError);
                    return;
                }
            }

            try {
                JSONObject localPulse = readPrivateJsonIfExists(LOCAL_PULSE_FILE);
                boolean armed = getPreferences(MODE_PRIVATE).getBoolean("backup_body_armed", false);
                String rendered = GenesisDashboard.render(snapshot, localPulse, armed, live);
                boolean finalLive = live;
                runOnUiThread(() -> {
                    refreshBackupStatus();
                    status.setText("Dashboard: " + (finalLive ? "live" : "offline snapshot"));
                    reply.setText(rendered);
                });
            } catch (Exception e) {
                showError("Dashboard render failed", e);
            }
        });
    }

    private void checkHealth() {
        status.setText("Status: checking…");
        executor.submit(() -> {
            try {
                String body = request("GET", normalizedBaseUrl() + "/health", null, false);
                JSONObject json = new JSONObject(body);
                runOnUiThread(() -> status.setText("Status: " + json.optString("status", "connected")));
            } catch (Exception e) {
                showError("Status check failed", e);
            }
        });
    }

    private void toggleBackupBody() {
        boolean armed = !getPreferences(MODE_PRIVATE).getBoolean("backup_body_armed", false);
        getPreferences(MODE_PRIVATE).edit().putBoolean("backup_body_armed", armed).apply();
        refreshBackupStatus();
    }

    private void refreshBackupStatus() {
        boolean armed = getPreferences(MODE_PRIVATE).getBoolean("backup_body_armed", false);
        File snapshot = new File(getFilesDir(), SNAPSHOT_FILE);
        File candidate = new File(getFilesDir(), RECONCILE_FILE);
        String snapshotText = snapshot.exists() ? "snapshot saved" : "no snapshot";
        String candidateText = candidate.exists() ? " · candidate pending" : "";
        if (backupStatus != null) {
            backupStatus.setText("Backup body: " + (armed ? "ARMED" : "standby") + " · " + snapshotText + candidateText);
        }
    }

    private void syncBackupState() {
        backupStatus.setText("Backup body: syncing Genesis state…");
        executor.submit(() -> {
            try {
                String body = request("GET", normalizedBaseUrl() + "/v1/owner/dashboard", null, true);
                JSONObject json = new JSONObject(body);
                json.put("phone_backup_snapshot", true);
                json.put("snapshot_epoch_ms", System.currentTimeMillis());
                writePrivateJson(SNAPSHOT_FILE, json);
                runOnUiThread(() -> {
                    refreshBackupStatus();
                    Toast.makeText(this, "Genesis backup state saved on phone", Toast.LENGTH_SHORT).show();
                });
            } catch (Exception e) {
                showError("Backup state sync failed", e);
                runOnUiThread(this::refreshBackupStatus);
            }
        });
    }

    private void runLocalEmergencyPulse() {
        if (!getPreferences(MODE_PRIVATE).getBoolean("backup_body_armed", false)) {
            Toast.makeText(this, "Arm the backup body first", Toast.LENGTH_SHORT).show();
            return;
        }

        reply.setText("Running one bounded local Genesis pulse…");
        executor.submit(() -> {
            try {
                JSONObject snapshot = readPrivateJson(SNAPSHOT_FILE);
                JSONObject previous = readPrivateJsonIfExists(LOCAL_PULSE_FILE);
                JSONObject result = EmergencyPulseEngine.runOnePulse(snapshot, previous);
                int attempts = previous == null ? 1 : previous.optInt("local_attempts", 0) + 1;
                result.put("local_attempts", attempts);
                writePrivateJson(LOCAL_PULSE_FILE, result);
                writePrivateJson(RECONCILE_FILE, result);
                runOnUiThread(() -> {
                    refreshBackupStatus();
                    reply.setText("Emergency pulse complete\nMode: " + result.optString("mode")
                            + "\nIssue: " + result.optString("focused_issue_id", "none")
                            + "\nNext: " + result.optString("next_step")
                            + "\n\nResult is candidate-only and awaits normal Genesis validation.");
                });
            } catch (Exception e) {
                showError("Emergency pulse failed", e);
            }
        });
    }

    private void viewPendingCandidate() {
        executor.submit(() -> {
            try {
                JSONObject candidate = readPrivateJson(RECONCILE_FILE);
                String rendered = candidate.toString(2);
                runOnUiThread(() -> reply.setText(rendered));
            } catch (Exception e) {
                showError("No reconciliation candidate", e);
            }
        });
    }

    private void viewOfflineBackup() {
        executor.submit(() -> {
            try {
                JSONObject snapshot = readPrivateJson(SNAPSHOT_FILE);
                JSONObject localPulse = readPrivateJsonIfExists(LOCAL_PULSE_FILE);
                boolean armed = getPreferences(MODE_PRIVATE).getBoolean("backup_body_armed", false);
                String rendered = GenesisDashboard.render(snapshot, localPulse, armed, false);
                runOnUiThread(() -> reply.setText(rendered));
            } catch (Exception e) {
                showError("Offline backup unavailable", e);
            }
        });
    }

    private JSONObject readPrivateJson(String filename) throws Exception {
        File file = new File(getFilesDir(), filename);
        if (!file.exists()) throw new IllegalStateException("Required local Genesis state is not available");
        StringBuilder body = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(new FileInputStream(file), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) body.append(line);
        }
        return new JSONObject(body.toString());
    }

    private JSONObject readPrivateJsonIfExists(String filename) throws Exception {
        File file = new File(getFilesDir(), filename);
        return file.exists() ? readPrivateJson(filename) : null;
    }

    private void writePrivateJson(String filename, JSONObject json) throws Exception {
        try (FileOutputStream out = openFileOutput(filename, MODE_PRIVATE)) {
            out.write(json.toString().getBytes(StandardCharsets.UTF_8));
        }
    }

    private void sendMessage() {
        String text = message.getText().toString().trim();
        if (text.isEmpty()) {
            Toast.makeText(this, "Enter a message", Toast.LENGTH_SHORT).show();
            return;
        }
        reply.setText("Genesis is responding…");
        executor.submit(() -> {
            try {
                JSONObject payload = new JSONObject();
                payload.put("sender", "genesis-android");
                payload.put("message", text);
                String body = request("POST", normalizedBaseUrl() + "/v1/message", payload.toString(), true);
                JSONObject json = new JSONObject(body);
                String response = json.optString("response", json.toString());
                runOnUiThread(() -> reply.setText(response));
            } catch (Exception e) {
                showError("Message failed", e);
            }
        });
    }

    private String request(String method, String endpoint, String payload, boolean authenticated) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(endpoint).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(10000);
        connection.setReadTimeout(30000);
        connection.setRequestProperty("Accept", "application/json");

        if (authenticated) {
            String bearer = token.getText().toString().trim();
            if (bearer.isEmpty()) throw new IllegalArgumentException("Bearer token is required");
            connection.setRequestProperty("Authorization", "Bearer " + bearer);
        }

        if (payload != null) {
            byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream out = connection.getOutputStream()) {
                out.write(bytes);
            }
        }

        int code = connection.getResponseCode();
        InputStream input = code >= 200 && code < 300 ? connection.getInputStream() : connection.getErrorStream();
        StringBuilder body = new StringBuilder();
        if (input != null) {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(input, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) body.append(line);
            }
        }
        connection.disconnect();
        if (code < 200 || code >= 300) throw new IllegalStateException("HTTP " + code + ": " + body);
        return body.toString();
    }

    private void showError(String prefix, Exception error) {
        runOnUiThread(() -> {
            String text = prefix + ": " + error.getMessage();
            status.setText(text);
            reply.setText(text);
        });
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }
}

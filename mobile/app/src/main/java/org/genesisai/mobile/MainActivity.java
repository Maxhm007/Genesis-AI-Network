package org.genesisai.mobile;

import android.app.Activity;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private EditText baseUrl;
    private EditText token;
    private EditText message;
    private TextView status;
    private TextView reply;

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
        subtitle.setText("Secure mobile client for Genesis Core");
        subtitle.setPadding(0, 0, 0, 24);
        root.addView(subtitle);

        baseUrl = field("Genesis API URL (HTTPS)", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        baseUrl.setText(getPreferences(MODE_PRIVATE).getString("base_url", ""));
        root.addView(baseUrl);

        token = field("Bearer token (not stored)", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        root.addView(token);

        Button healthButton = new Button(this);
        healthButton.setText("Check Genesis Status");
        healthButton.setOnClickListener(v -> checkHealth());
        root.addView(healthButton);

        status = new TextView(this);
        status.setText("Status: not connected");
        status.setPadding(0, 8, 0, 24);
        root.addView(status);

        message = field("Message Genesis", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        message.setMinLines(4);
        root.addView(message);

        Button sendButton = new Button(this);
        sendButton.setText("Send");
        sendButton.setOnClickListener(v -> sendMessage());
        root.addView(sendButton);

        reply = new TextView(this);
        reply.setText("Genesis reply will appear here.");
        reply.setPadding(0, 24, 0, 32);
        root.addView(reply);

        TextView security = new TextView(this);
        security.setText("Security: remote cleartext HTTP is disabled. Configure an HTTPS Genesis endpoint. The token is kept only in memory for this app session.");
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
        if (!value.startsWith("https://")) {
            throw new IllegalArgumentException("Use an HTTPS Genesis API URL");
        }
        getPreferences(MODE_PRIVATE).edit().putString("base_url", value).apply();
        return value;
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

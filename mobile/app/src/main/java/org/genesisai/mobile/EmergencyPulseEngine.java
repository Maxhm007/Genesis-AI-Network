package org.genesisai.mobile;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Bounded Android-side emergency pulse engine.
 *
 * This does not mutate canonical Genesis code. It consumes the latest mirrored
 * owner snapshot, selects/continues exactly one issue, produces one candidate
 * next-step record, and returns it for app-private persistence/reconciliation.
 */
public final class EmergencyPulseEngine {
    private EmergencyPulseEngine() {}

    public static JSONObject runOnePulse(JSONObject snapshot, JSONObject previousLocalState) throws Exception {
        if (snapshot == null) throw new IllegalArgumentException("Genesis snapshot is required");

        JSONObject result = new JSONObject();
        result.put("schema_version", 1);
        result.put("genesis_identity", "Genesis");
        result.put("body", "android_backup_body");
        result.put("candidate_only", true);
        result.put("canonical_mutation_allowed", false);
        result.put("created_epoch_ms", System.currentTimeMillis());

        String previousIssue = previousLocalState == null ? "" : previousLocalState.optString("focused_issue_id", "");
        JSONObject tasks = snapshot.optJSONObject("tasks");
        JSONArray highPriority = tasks == null ? null : tasks.optJSONArray("high_priority");

        JSONObject selected = null;
        if (highPriority != null) {
            for (int i = 0; i < highPriority.length(); i++) {
                JSONObject item = highPriority.optJSONObject(i);
                if (item == null) continue;
                String id = issueId(item, i);
                if (!previousIssue.isEmpty() && previousIssue.equals(id)) {
                    selected = item;
                    break;
                }
            }
            if (selected == null && highPriority.length() > 0) selected = highPriority.optJSONObject(0);
        }

        if (selected != null) {
            String issueId = issueId(selected, 0);
            result.put("mode", "issue");
            result.put("focused_issue_id", issueId);
            result.put("issue", selected);
            result.put("action", "continue_same_issue");
            result.put("next_step", deriveNextStep(selected, previousLocalState));
        } else {
            result.put("mode", "discovery");
            result.put("focused_issue_id", "");
            result.put("action", "bounded_local_discovery");
            result.put("next_step", "Review cached Genesis state for capability gaps, unresolved/deferred work, stale health signals, or a logical new learning target. Record findings as candidate evidence only.");
        }

        result.put("requires_network_validation", true);
        result.put("reconcile_status", "pending");
        return result;
    }

    private static String issueId(JSONObject item, int fallbackIndex) {
        String id = item.optString("task_id", "");
        if (id.isEmpty()) id = item.optString("id", "");
        if (id.isEmpty()) id = item.optString("issue_id", "");
        if (id.isEmpty()) id = "snapshot-task-" + fallbackIndex;
        return id;
    }

    private static String deriveNextStep(JSONObject issue, JSONObject previousLocalState) {
        int attempts = previousLocalState == null ? 0 : previousLocalState.optInt("local_attempts", 0);
        String title = issue.optString("title", issue.optString("description", "current Genesis issue"));
        if (attempts == 0) {
            return "Analyze " + title + "; identify the smallest testable next action using only cached/local evidence.";
        }
        return "Retry " + title + " with a changed method; preserve the same issue focus, record why the prior approach was insufficient, and produce one new candidate action.";
    }
}

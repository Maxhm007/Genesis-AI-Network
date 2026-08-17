package org.genesisai.mobile;

import org.json.JSONObject;

public final class GenesisDashboard {
    private GenesisDashboard() {}

    public static String render(JSONObject snapshot, JSONObject localPulse, boolean armed, boolean live) {
        JSONObject tasks = snapshot == null ? null : snapshot.optJSONObject("tasks");
        JSONObject modules = snapshot == null ? null : snapshot.optJSONObject("module_summary");
        JSONObject security = snapshot == null ? null : snapshot.optJSONObject("security");
        JSONObject learning = snapshot == null ? null : snapshot.optJSONObject("self_learning");
        JSONObject scorecard = snapshot == null ? null : snapshot.optJSONObject("scorecard");

        int openTasks = tasks == null ? 0 : tasks.optInt("open_count", 0);
        int moduleCount = modules == null ? 0 : modules.optInt("module_count", 0);
        int activeModules = modules == null ? 0 : modules.optInt("active_module_count", 0);
        String securityState = security == null ? "unknown" : security.optString("status", "unknown");
        String learningState = learning == null ? "unknown" : learning.optString("status", "available");
        String overall = scorecard == null ? "unmeasured" : scorecard.optString("status", scorecard.optString("grade", "measured"));

        String issue = "none";
        String pulseMode = "standby";
        int attempts = 0;
        if (localPulse != null) {
            issue = localPulse.optString("focused_issue_id", "none");
            pulseMode = localPulse.optString("mode", "local");
            attempts = localPulse.optInt("local_attempts", 0);
        }

        return "GENESIS DASHBOARD\n"
                + "Identity: Genesis = 1\n"
                + "Source: " + (live ? "LIVE" : "OFFLINE SNAPSHOT") + "\n"
                + "Overall: " + overall + "\n\n"
                + "WORK\n"
                + "Open issues/tasks: " + openTasks + "\n"
                + "Focused issue: " + issue + "\n"
                + "Local pulse mode: " + pulseMode + "\n"
                + "Local attempts: " + attempts + "\n\n"
                + "SYSTEM\n"
                + "Modules: " + activeModules + "/" + moduleCount + " active\n"
                + "Security: " + securityState + "\n"
                + "Learning: " + learningState + "\n\n"
                + "PHONE BODY\n"
                + "Backup body: " + (armed ? "ARMED" : "STANDBY") + "\n"
                + "Primary continuity: Gene Pulse Network\n"
                + "Phone authority: candidate-only";
    }
}

// ops-watchdog: an external dead-man's switch for the repository-health
// supervisor, run by Cloudflare's cron rather than GitHub's. See checks.js.
import { runChecks } from "./checks.js";

export default {
  async scheduled(controller, env, ctx) {
    const cache = typeof caches !== "undefined" ? caches.default : undefined;
    ctx.waitUntil(
      runChecks(env, new Date(controller.scheduledTime), { fetch, cache }).then((report) => {
        console.log(JSON.stringify({
          store: report.store, alerts: report.alerts.length, sent: report.sent,
          supervisor_age_hours: report.supervisor && report.supervisor.age_hours,
          core_age_hours: report.core && report.core.age_hours,
          d1: report.d1 && report.d1.ok ? "ok" : report.d1 && report.d1.error,
        }));
      }),
    );
  },

  // The Worker has no public surface: nothing here reads or reveals state, so
  // a request cannot trigger checks or leak anything.
  async fetch() {
    return new Response("ops-watchdog: scheduled checks only\n", {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  },
};

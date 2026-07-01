import assert from "node:assert/strict";
import test from "node:test";

const missingSecretInSettings =
  /is not configured in settings.*secrets and variables.*actions/;

test("classifies Drive Intake missing Google credentials as credentials", () => {
  const log =
    "GOOGLE_APPLICATION_CREDENTIALS_JSON is not configured in Settings → Secrets and variables → Actions.";
  assert.match(log.toLowerCase(), missingSecretInSettings);
});

test("does not classify generic build failures as missing credentials", () => {
  const log = "ModuleNotFoundError: No module named 'googleapiclient'";
  assert.doesNotMatch(log.toLowerCase(), missingSecretInSettings);
});

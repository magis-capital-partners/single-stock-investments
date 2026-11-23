import { privateJson, requireHumanViewer } from "../../../_lib/auth.js";
import { readPaperExecution } from "../../../_lib/rs-execution.js";

export async function onRequestGet(context) {
  const viewer = await requireHumanViewer(context);
  if (viewer?.role !== "owner") return privateJson({ error: "Owner access required." }, viewer ? 403 : 401);
  return readPaperExecution(context);
}

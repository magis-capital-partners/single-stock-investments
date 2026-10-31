import { requirePortfolioViewer, privateJson } from '../../../_lib/auth.js';
import { failure, requestId, requireDatabase } from '../../../_lib/http.js';
import { loadRealized } from '../../../_lib/realized.js';

export async function onRequestGet(context) {
  const id = requestId(context.request);
  if (!await requirePortfolioViewer(context)) return privateJson({ error: 'Unauthorized.', request_id: id }, 401);
  try {
    return privateJson({ ...await loadRealized(requireDatabase(context.env), new URL(context.request.url).searchParams), request_id: id });
  } catch (error) {
    if (error instanceof TypeError) return privateJson({ error: error.message, request_id: id }, 400);
    return failure(error, id);
  }
}

const BLACKLISTED_FIELDS = new Set([
  'payload', 'raw', 'fhir', 'requestBody', 'responseBody',
  'complaintText', 'otp', 'nationalId', 'iqama', 'email', 'phone',
]);

export function sanitizeResponse<T extends Record<string, unknown>>(data: T): T {
  if (data === null || data === undefined || typeof data !== 'object') return data;
  if (Array.isArray(data)) {
    return data.map((item) =>
      typeof item === 'object' && item !== null
        ? sanitizeResponse(item as Record<string, unknown>)
        : item
    ) as unknown as T;
  }
  const cleaned: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(data)) {
    if (BLACKLISTED_FIELDS.has(key)) continue;
    if (typeof value === 'object' && value !== null) {
      cleaned[key] = sanitizeResponse(value as Record<string, unknown>);
    } else {
      cleaned[key] = value;
    }
  }
  return cleaned as T;
}

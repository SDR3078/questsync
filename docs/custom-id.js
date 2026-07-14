// custom-id.js — the ONE encoder, shared by index.html and custom-id.test.mjs.
//
// It must reproduce WardStone's encode_custom_id (private repo:
// src/wardstone/processors/paypal.py) byte-for-byte:
//
//     custom_id = "1|" + b64url(utf8(product)) + "|" + b64url(utf8(subject))
//
// where b64url is URL-safe base64 (- and _, never + or /) with "=" padding stripped.
//
// This codec is NOT a secret: access is gated by the Habitica API token at CalDAV
// login, never by hiding this format. So it lives in the open engine repo, and
// custom-id.golden.json (generated FROM WardStone's own function) pins the two
// implementations together — see custom-id.test.mjs.

export const CUSTOM_ID_VERSION = "1";

// base64url of a string's UTF-8 bytes, padding stripped.
// Matches Python: base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
export function b64url(raw) {
  const bytes = new TextEncoder().encode(raw); // UTF-8 — same bytes as Python str.encode()
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b); // Uint8Array -> binary string for btoa
  return btoa(bin) // standard base64 (uses + / and = padding)
    .replace(/\+/g, "-") // -> URL-safe alphabet
    .replace(/\//g, "_")
    .replace(/=+$/, ""); // strip padding, like Python's rstrip("=")
}

// Encode (product, subject) into a PayPal subscription custom_id.
// subject is opaque and may contain the "|" delimiter, so both halves are base64url'd.
export function encodeCustomId(product, subject) {
  return `${CUSTOM_ID_VERSION}|${b64url(product)}|${b64url(subject)}`;
}

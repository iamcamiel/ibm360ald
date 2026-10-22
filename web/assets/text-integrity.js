// Hash the exact fetched bytes before decoding, including any UTF-8 BOM and EOLs.
// Unverified text remains readable; geometry and navigation must stay disabled.
export async function readVerifiedText(bytes, expectedSha256, crypto = globalThis.crypto) {
  let verified = false;
  let reason = 'The catalogue is missing a valid page fingerprint.';
  if (/^[a-f0-9]{64}$/.test(expectedSha256 || '')) {
    reason = 'This browser cannot verify page text here. Try HTTPS or localhost.';
  }
  if (/^[a-f0-9]{64}$/.test(expectedSha256 || '') && crypto?.subtle?.digest) {
    try {
      const hash = await crypto.subtle.digest('SHA-256', bytes);
      const actual = Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
      verified = actual === expectedSha256;
      reason = 'Page text and catalogue are different versions. Reload ALDbrowser; if this persists, the site catalogue needs refreshing.';
    } catch { reason = 'The browser could not complete the page fingerprint check.'; }
  }
  return {
    text: new TextDecoder('utf-8', { fatal: true }).decode(bytes),
    interactionsAllowed: verified,
    notice: verified ? '' : `${reason} Wire selection and page links are disabled for this page.`,
  };
}

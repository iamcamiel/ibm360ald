// Hash the exact fetched bytes before decoding, including any UTF-8 BOM and EOLs.
// Unverified text remains readable; geometry and navigation must stay disabled.
export async function readVerifiedText(bytes, expectedSha256, crypto = globalThis.crypto) {
  let verified = false;
  if (/^[a-f0-9]{64}$/.test(expectedSha256 || '') && crypto?.subtle?.digest) {
    try {
      const hash = await crypto.subtle.digest('SHA-256', bytes);
      const actual = Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
      verified = actual === expectedSha256;
    } catch { /* Fail closed for interactions while keeping the page readable. */ }
  }
  return {
    text: new TextDecoder('utf-8', { fatal: true }).decode(bytes),
    interactionsAllowed: verified,
    notice: verified ? '' : 'Page text could not be verified against the catalogue. Wire selection and page links are disabled for this page.',
  };
}

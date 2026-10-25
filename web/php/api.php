<?php
declare(strict_types=1);
require_once __DIR__ . '/catalogue.php';
require_once __DIR__ . '/interactions.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-cache');
header('X-Content-Type-Options: nosniff');
// A cold clone may need to index explicit cross-page references once.
if (function_exists('set_time_limit')) @set_time_limit(180);
try {
    $root = $aldRepositoryRoot ?? dirname(__DIR__, 2);
    $store = new \ALDbrowser\Store($root);
    $id = $_GET['entry'] ?? $_GET['interaction'] ?? $_GET['text'] ?? null;
    if ($id !== null && (!is_string($id) || !preg_match('/^[a-f0-9]{64}$/D', $id))) {
        http_response_code(400); throw new InvalidArgumentException('Invalid page identity.');
    }
    $catalogue = $store->catalogue($id);
    if (isset($_GET['text'])) {
        $text=$store->text($store->page($id,$catalogue));header('Content-Type: text/plain; charset=utf-8');echo $text;exit;
    } elseif (isset($_GET['interaction'])) $response = \ALDbrowser\interactions($store, $store->page($id, $catalogue), $catalogue);
    elseif ($id !== null) $response = \ALDbrowser\public_entry($store->page($id, $catalogue));
    else {
        $response = $catalogue; unset($response['signature']);
        $response['pages'] = array_map('ALDbrowser\\public_entry', $response['pages']);
    }
    $bytes = \ALDbrowser\json_bytes($response); $etag = '"' . hash('sha256', $bytes) . '"';
    header('ETag: ' . $etag);
    if (($_SERVER['HTTP_IF_NONE_MATCH'] ?? '') === $etag) http_response_code(304);
    else echo $bytes;
} catch (OutOfBoundsException $e) {
    http_response_code(404); echo '{"error":"Page is unavailable."}';
} catch (Throwable $e) {
    if (http_response_code() < 400) http_response_code(503);
    header('Retry-After: 1');
    error_log('ALDbrowser: ' . $e->getMessage());
    echo '{"error":"The page data could not be refreshed. Please retry."}';
}

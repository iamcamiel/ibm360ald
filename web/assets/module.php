<?php
declare(strict_types=1);

// Serve the complete module graph through revalidated URLs. Versioning only
// browser.js leaves its relative imports in the browser's old static cache.
$modules = ['browser.js', 'geometry.js', 'interactions.js', 'page-source.js', 'text-integrity.js'];
$name = $_GET['file'] ?? '';
if (!is_string($name) || !in_array($name, $modules, true)) {
    http_response_code(404);
    exit;
}
$source = file_get_contents(__DIR__ . '/' . $name);
if ($source === false) {
    http_response_code(503);
    exit;
}
$source = preg_replace_callback(
    '~(from\s+[\x27\x22])\./([a-z-]+\.js)([\x27\x22])~',
    static function (array $match) use ($modules): string {
        if (!in_array($match[2], $modules, true)) {
            throw new RuntimeException('Unknown viewer dependency');
        }
        return $match[1] . './module.php?file=' . $match[2] . $match[3];
    },
    $source
);
$etag = '"' . hash('sha256', $source) . '"';
header('Content-Type: application/javascript; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Cache-Control: no-cache');
header('ETag: ' . $etag);
if (($_SERVER['HTTP_IF_NONE_MATCH'] ?? '') === $etag) {
    http_response_code(304);
    exit;
}
echo $source;

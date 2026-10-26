<?php
declare(strict_types=1);
require_once dirname(__DIR__) . '/php/strict-json.php';

function check(bool $passed, string $message): void {
    if (!$passed) throw new RuntimeException($message);
}
function rejects(string $json, bool $associative): void {
    try { \ALDbrowser\strict_json_decode($json, $associative); }
    catch (Throwable $error) { return; }
    throw new RuntimeException('Invalid or duplicate-bearing JSON was accepted.');
}

$long = str_repeat('x', 300000);
foreach ([true, false] as $associative) {
    $valid = '{"text":"' . $long . '","nested":{"value":1},"other":{"value":2}}';
    check(\ALDbrowser\strict_json_decode($valid, $associative) == json_decode($valid, $associative, 512, JSON_THROW_ON_ERROR), 'Long valid payload changed.');
    // A regex tokenizer previously failed before reaching these duplicate keys.
    rejects('{"text":"' . $long . '","dup":1,"d\\u0075p":2}', $associative);
    foreach (['{"x":{"a":1,"a":2}}', '{"x":1e999}', '{"x":NaN}', '{"x":', "{\"x\":\"\xff\"}"] as $invalid) {
        rejects($invalid, $associative);
        rejects($invalid, $associative);
    }
    $escaped = '{"text":"quoted \\" text with } [ \\\\ end","1":1,"01":2,"empty":{},"array":[],"null":null}';
    check(\ALDbrowser\strict_json_decode($escaped, $associative) == json_decode($escaped, $associative, 512, JSON_THROW_ON_ERROR), 'Escaped string or native value types changed.');
}
$payload = '{"nested":{"value":1},"array":[],"object":{},"null":null}';
$first = \ALDbrowser\strict_json_decode($payload, true);
$first['nested']['value'] = 99;
$second = \ALDbrowser\strict_json_decode($payload, false);
check($second instanceof stdClass && $second->nested->value === 1 && $second->object instanceof stdClass && is_array($second->array) && $second->null === null, 'Memo reused decoded values or wrong associative mode.');
$second->nested->value = 88;
check(\ALDbrowser\strict_json_decode($payload, true)['nested']['value'] === 1, 'Nested mutation leaked into a later call.');
$initial = '{"serial":-1}';
\ALDbrowser\strict_json_decode($initial);
for ($i=0; $i<4100; $i++) \ALDbrowser\strict_json_decode('{"serial":'.$i.'}');
$variables = (new ReflectionFunction('ALDbrowser\\strict_json_decode'))->getStaticVariables();
check(count($variables['validated']) === 4096, 'Validation memo is not bounded.');
check(!isset($variables['validated'][hash('sha256', $initial)]), 'Old validation digest was not evicted.');
check(\ALDbrowser\strict_json_decode($initial)['serial'] === -1, 'Eviction changed a later decode.');
echo "Strict JSON regressions passed.\n";

<?php
declare(strict_types=1);

namespace ALDbrowser;
require_once __DIR__.'/strict-json.php';

// The repository files are authoritative. These caches live outside the clone.
function json_read(string $file): array {
    $value = strict_json_decode((string)file_get_contents($file),true);
    if (!is_array($value)) throw new \RuntimeException('Expected JSON data.');
    return $value;
}
function json_bytes($value): string {
    return json_encode($value, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR) . "\n";
}
function ulen(string $s): int { return preg_match_all('/./us', $s); }
function usub(string $s, int $start, ?int $length = null): string {
    $chars = preg_split('//u', $s, -1, PREG_SPLIT_NO_EMPTY);
    return implode('', array_slice($chars, $start, $length));
}
function lines(string $text): array {
    $text = preg_replace('/^\xEF\xBB\xBF/', '', $text);
    if ($text === '') return [];
    $rows = preg_split('/\r\n|\r|\n/', $text);
    if (preg_match('/[\r\n]$/', $text)) array_pop($rows);
    return $rows;
}
function source_path(string $root, string $relative): string {
    $relative = str_replace('\\', '/', $relative);
    if (!preg_match('~^(?:ALD|json|Card-ALD|notes)/~', $relative) ||
        preg_match('~(?:^|/)(?:\.|\.\.)(?:/|$)|[:\x00]|//~', $relative)) {
        throw new \RuntimeException('Invalid source identity.');
    }
    $path = realpath($root . '/' . $relative);
    if ($path === false || !is_file($path) ||
        strncmp(str_replace('\\', '/', $path), str_replace('\\', '/', $root) . '/', strlen($root) + 1) !== 0) {
        throw new \RuntimeException('Source file is unavailable.');
    }
    return $path;
}
function source_url(string $relative, string $sha): string {
    return implode('/', array_map('rawurlencode', explode('/', str_replace('\\', '/', $relative)))) . '?v=' . $sha;
}


// Same typed canonical digest as tools/normalization/review.py. Objects and
// arrays remain distinct, including empty values; no JSON re-encoding needed.
function content_digest($document): string {
    $context=hash_init('sha256');
    $walk=function($value) use (&$walk,$context): void {
        if ($value===null) hash_update($context,'N');
        elseif (is_bool($value)) hash_update($context,$value?'B1':'B0');
        elseif (is_int($value)) { $s=(string)$value;hash_update($context,'I'.strlen($s).':'.$s); }
        elseif (is_float($value)) { if(!is_finite($value))throw new \RuntimeException('Nonfinite content');hash_update($context,'F'.pack('E',$value)); }
        elseif (is_string($value)) hash_update($context,'S'.strlen($value).':'.$value);
        elseif (is_array($value)) { hash_update($context,'A'.count($value).':');foreach($value as $item)$walk($item); }
        elseif ($value instanceof \stdClass) { $items=get_object_vars($value);ksort($items,SORT_STRING);hash_update($context,'O'.count($items).':');foreach($items as $key=>$item){$walk($key);$walk($item);} }
        else throw new \RuntimeException('Invalid content value');
    };
    $body=clone $document;unset($body->review);$walk($body);return hash_final($context);
}
function approved_content(string $bytes): bool {
    try {
        $document=strict_json_decode($bytes,false);$review=$document->review??null;
        return ($document->schema??'')==='ibm360-ald-page-v3' && ($review->user_approved??false)===true &&
            ($review->status??'')==='approved' && is_string($review->approval_statement??null) && trim($review->approval_statement)!=='' &&
            is_string($review->approved_at??null) && hash_equals($review->content_sha256??'',content_digest($document));
    } catch (\Throwable $error) { return false; }
}


const V4_SCHEMA = 'https://raw.githubusercontent.com/iamcamiel/ibm360ald/main/schema/ALD_v4.json';
function is_v4(array $model): bool { return ($model['$schema']??null)===V4_SCHEMA; }
function v4_review_signature(string $path): array {
    $model=json_read($path); if(!is_v4($model))return [];
    $ref=$model['review']['details']??null;
    if($ref===null)return [hash_file('sha256',$path),null];
    if(!is_string($ref)||!preg_match('~^(?!/)(?!.*(?:^|/)\.{1,2}(?:/|$))[^\\\\:\x00]+$~D',$ref))throw new \RuntimeException('Unsafe review details path.');
    $target=realpath(dirname($path).'/'.$ref);$base=realpath(dirname($path));
    if($target===false||!is_file($target)||strpos($target,$base.DIRECTORY_SEPARATOR)!==0)throw new \RuntimeException('Review details are missing or outside the page directory.');
    return [hash_file('sha256',$path),hash_file('sha256',$target)];
}
function v4_renderer_path(): string { return getenv('ALDBROWSER_V4_RENDERER')?:dirname(__DIR__,2).'/tools/ald_render.py'; }
function native_v4_view(string $path): array {
    $python=getenv('ALDBROWSER_PYTHON')?:(PHP_OS_FAMILY==='Windows'?'python':'python3');
    $renderer=v4_renderer_path();
    if(!is_file($renderer)||@hash_file('sha256',$renderer)===false)throw new \RuntimeException('Configure ALDBROWSER_V4_RENDERER to the qualified standalone renderer.');
    $pipes=[];$process=proc_open([$python,'-B','-X','utf8',__DIR__.'/v4_view.py',$path,$renderer],[0=>['pipe','r'],1=>['pipe','w'],2=>['pipe','w']],$pipes);
    if(!is_resource($process))throw new \RuntimeException('Could not start the functional page renderer.');
    fclose($pipes[0]);$result=stream_get_contents($pipes[1]);fclose($pipes[1]);$error=stream_get_contents($pipes[2]);fclose($pipes[2]);$code=proc_close($process);
    if($code!==0){error_log($error);throw new \RuntimeException('Functional page or content-bound review is invalid.');}
    $value=json_decode($result,true,512,JSON_THROW_ON_ERROR);
    if(($value['format']??null)!=='v4'||!is_string($value['text']??null))throw new \RuntimeException('Invalid functional renderer response.');
    return $value;
}
final class Store {
    public string $root;
    public string $cache;
    public string $engine;
    public function __construct(string $root, ?string $cache = null) {
        $this->root = (string)realpath($root);
        if ($this->root === '') throw new \RuntimeException('Repository is unavailable.');
        $this->engine = hash('sha256', file_get_contents(__FILE__) . file_get_contents(__DIR__ . '/interactions.php') . file_get_contents(__DIR__.'/v4_view.py') . file_get_contents(__DIR__.'/strict-json.php') . (is_file(v4_renderer_path())?(@hash_file('sha256',v4_renderer_path())?:'renderer-unavailable'):'renderer-unavailable'));
        $this->cache = $cache ?? (getenv('ALDBROWSER_CACHE_DIR') ?: sys_get_temp_dir() . '/aldbrowser-' . substr(hash('sha256', $this->root), 0, 24));
        if (!is_dir($this->cache) && !@mkdir($this->cache, 0700, true) && !is_dir($this->cache)) {
            throw new \RuntimeException('ALDbrowser needs a writable temporary cache directory.');
        }
    }
    public function get(string $key): ?array {
        $p = $this->cache . '/' . hash('sha256', $this->engine . $key) . '.json';
        if (!is_file($p)) return null;
        try { return json_read($p); } catch (\Throwable $e) { return null; }
    }
    public function put(string $key, array $value): void {
        $p = $this->cache . '/' . hash('sha256', $this->engine . $key) . '.json';
        $tmp = tempnam($this->cache, '.write-');
        try {
            if (file_put_contents($tmp, json_bytes($value), LOCK_EX) === false || !rename($tmp, $p)) throw new \RuntimeException('Could not update the browser cache.');
        } finally { if (is_file($tmp)) unlink($tmp); }
    }
    public function locked(string $key, callable $work) {
        $lock = fopen($this->cache . '/' . hash('sha256', $this->engine . $key) . '.lock', 'c');
        if (!$lock || !flock($lock, LOCK_EX)) throw new \RuntimeException('Could not lock the browser cache.');
        try { return $work(); } finally { flock($lock, LOCK_UN); fclose($lock); }
    }
    private function statKey(string $relative): array {
        $p = source_path($this->root, $relative); clearstatcache(true, $p); $s = stat($p);
        return [$relative, $s['mtime'], $s['ctime'], $s['size']];
    }
    public function catalogue(?string $fresh = null): array {
        $statusPath = source_path($this->root, 'notes/Source status.json');
        $status = json_read($statusPath); $specs = []; $signatures = [];
        foreach ($status['records'] as $record) {
            $jp = str_replace('\\', '/', $record['repository']['json']['path']);
            $tp = str_replace('\\', '/', $record['repository']['txt']['path']);
            if (strpos($jp, 'json/') !== 0 || substr($jp, -5) !== '.json' || strpos($tp, 'ALD/') !== 0 || substr($tp, -4) !== '.txt' || isset($specs[hash('sha256',$jp)])) throw new \RuntimeException('Invalid or repeated published page identity.');
            $id = hash('sha256', $jp); $sig = [$this->statKey($jp), $this->statKey($tp), $record['page'], $record['repository']['json']['sha256'], $record['repository']['txt']['sha256']];
            $sig[]=v4_review_signature(source_path($this->root,$jp));
            $specs[$id] = ['id'=>$id, 'model'=>$jp, 'text'=>$tp, 'record'=>$record, 'sig'=>$sig];
            $signatures[] = $sig;
        }
        $cardFiles = glob($this->root . '/Card-ALD/*.txt'); sort($cardFiles, SORT_STRING);
        foreach ($cardFiles as $p) {
            if (!preg_match('/^(\d{4})(?:-(\d+))?\.txt$/D', basename($p), $m)) continue;
            $tp = 'Card-ALD/' . basename($p); $jp = null;
            foreach (['json/Card-ALD/definitions/' . $m[1] . '.json', 'json/Card-ALD/' . $m[1] . '.json'] as $candidate) {
                if (is_file($this->root . '/' . $candidate)) { $jp = $candidate; break; }
            }
            $id = hash('sha256', $tp); $sig = [$this->statKey($tp), $jp ? $this->statKey($jp) : null];
            $sig[]=v4_review_signature(source_path($this->root,$jp));
            $specs[$id] = ['id'=>$id, 'model'=>$jp, 'text'=>$tp, 'card'=>$m[1], 'variant'=>$m[2] ?? null, 'sig'=>$sig];
            $signatures[] = $sig;
        }
        $signature = hash('sha256', json_bytes([$signatures, hash_file('sha256', $statusPath)]));
        $cached = $this->get('catalogue');
        if ($fresh === null && ($cached['signature'] ?? '') === $signature) return $cached;
        return $this->locked('catalogue', function () use ($specs, $signature, $fresh, $statusPath) {
            $entries = [];
            foreach ($specs as $id=>$spec) {
                $meta = $this->get('entry-' . $id);
                if (($meta['sig'] ?? null) !== $spec['sig'] || $id === $fresh) {
                    $meta = ['sig'=>$spec['sig'], 'entry'=>$this->entry($spec)];
                    $this->put('entry-' . $id, $meta);
                }
                $entries[] = $meta['entry'];
            }
            usort($entries, static function ($a, $b) {
                $key = static function ($e) { return [$e['type']==='card-ald' ? 1:0, strtolower($e['section']),
                    $e['type']==='card-ald' && $e['variant'] !== null ? $e['cardType'].'-'.sprintf('%09d',(int)$e['variant']+1) : ($e['displayPage'] ?? $e['page']), $e['title'], $e['id']]; };
                return $key($a) <=> $key($b);
            });
            $revision = hash('sha256', json_bytes(array_map(static function ($e) { return [$e['id'],$e['textSha256'],$e['jsonSha256'] ?? null]; }, $entries)));
            foreach ($entries as &$e) $e['interactionURL'] = 'catalogue.php?interaction='.$e['id'].'&v='.$revision;
            unset($e);
            $default = null; foreach ($entries as $e) if ($e['page']==='AP154' && $e['type']==='ald') { $default=$e; break; }
            $default = $default ?? $entries[0];
            $result = ['schema'=>'aldbrowser-catalogue-v1','signature'=>$signature,'revision'=>$revision,
                'sourceStatusSha256'=>hash_file('sha256',$statusPath),'pageCount'=>count($entries),
                'aldPageCount'=>count($specs)-count(array_filter($specs,static function($s){return isset($s['card']);})),
                'cardPageCount'=>count(array_filter($specs,static function($s){return isset($s['card']);})),
                'defaultPage'=>$default['page'],'defaultPageId'=>$default['id'],'pages'=>$entries,'delivery'=>'php-live-v1'];
            $this->put('catalogue',$result); return $result;
        });
    }
    private function entry(array $spec): array {
        $text = file_get_contents(source_path($this->root,$spec['text'])); $rows = lines($text); $sha = hash('sha256',$text);
        $modelBytes = $spec['model'] ? file_get_contents(source_path($this->root,$spec['model'])) : null;
        $model = $modelBytes !== null ? strict_json_decode($modelBytes,true) : [];
        if(array_key_exists('$schema',$model)&&!is_v4($model))throw new \RuntimeException('Unsupported functional page schema.');
        $msha = $modelBytes !== null ? hash('sha256',$modelBytes) : null;
        $reviewBefore=is_v4($model)?v4_review_signature(source_path($this->root,$spec['model'])):null;
        $v4=is_v4($model)?native_v4_view(source_path($this->root,$spec['model'])):null;
        if($v4!==null&&($v4['modelSha256']!==$msha||$reviewBefore!==v4_review_signature(source_path($this->root,$spec['model']))))throw new \RuntimeException('Page or review changed while rendering. Retry.');
        $publishedSha=$sha;
        if($v4!==null){$text=$v4['text'];$rows=lines($text);$sha=$v4['textSha256'];}
        $fileCode = explode(' ',pathinfo($spec['text'],PATHINFO_FILENAME),2)[0]; $card = $spec['card'] ?? null;
        $page = $card !== null ? pathinfo($spec['text'],PATHINFO_FILENAME) : $spec['record']['page'];
        if($v4!==null&&$v4['page']!==$page)throw new \RuntimeException('Functional page identity does not match the catalogue.');
        $title = $card !== null ? ($spec['variant']!==null ? 'Symbol variant '.$spec['variant'] : 'Canonical pinout') :
            ($model['page']['title'] ?? $model['current_extensions']['title'] ?? (explode(' ',pathinfo($spec['text'],PATHINFO_FILENAME),2)[1] ?? pathinfo($spec['text'],PATHINFO_FILENAME)));
        if(is_array($title))$title=implode(' ',$title);
        $subpage = null; if ($card===null && preg_match('/^'.preg_quote($page,'/').'-(\d+)$/D',$fileCode,$m)) $subpage=$m[1];
        $displayTitle = $title;
        if ($subpage!==null && !preg_match('/\bpage\s*0*'.(int)$subpage.'\b/i',$title)) $displayTitle.=' page '.$subpage;
        $parts=explode('/',$spec['text']); $section=$card!==null?'Card ALD':implode('/',array_slice($parts,1,-1));
        $e=['id'=>$spec['id'],'page'=>$page,'title'=>$title,'section'=>$section,'type'=>$card!==null?'card-ald':($v4!==null?'ald':($model['current_extensions']['page_type']??'ald')),
            'rows'=>count($rows),'columns'=>$rows ? max(array_map(__NAMESPACE__.'\\ulen',$rows)):0,'url'=>$v4!==null?'catalogue.php?text='.$spec['id'].'&v='.$sha:source_url($spec['text'],$sha),
            'textSha256'=>$sha,'modelSha256'=>$card!==null?null:$msha,'grid'=>['columnPitch'=>20,'rowPitch'=>30],
            'originalScan'=>null,'txtDownloadName'=>basename($spec['text']),'entryURL'=>'catalogue.php?entry='.$spec['id'],
            '_text'=>$spec['text'],'_model'=>$spec['model']];
        if ($card!==null) { $e['cardType']=$card;$e['variant']=$spec['variant']; }
        else { $e['displayPage']=$subpage!==null?$fileCode:$page;$e['displayTitle']=$displayTitle;$e['subpage']=$subpage; }
        if ($spec['model']) { $e['jsonURL']=source_url($spec['model'],$msha);$e['jsonSha256']=$msha;$e['jsonDownloadName']=$card!==null?$card.'.json':basename($spec['model']); }
        $e['_sourcePairCurrent']=$card!==null || ($spec['record']['repository']['json']['sha256']===$msha && $spec['record']['repository']['txt']['sha256']===$publishedSha);
        if($v4!==null){$e['format']='v4';$e['reviewStatus']=$v4['reviewStatus'];$e['reviewBound']=$v4['reviewBound'];$e['unresolvedCount']=$v4['unresolvedCount'];$e['_v4']=$v4;$e['_reviewSignature']=v4_review_signature(source_path($this->root,$spec['model']));}
        $e['userApproved']=$v4===null && $card===null && $e['_sourcePairCurrent'] && approved_content($modelBytes);
        return $e;
    }
    public function page(string $id, array $catalogue): array {
        foreach ($catalogue['pages'] as $e) if ($e['id']===$id) return $e;
        throw new \OutOfBoundsException('Page is unavailable.');
    }
    public function document(array $entry): array {
        if (!$entry['_model']) return [];
        $p=source_path($this->root,$entry['_model']);$data=file_get_contents($p);
        if (hash('sha256',$data)!==$entry['jsonSha256']) throw new \RuntimeException('Page changed while loading. Please retry.');
        return strict_json_decode($data,true);
    }
    public function text(array $entry): string {
        if(isset($entry['_v4'])){
            $this->document($entry);
            if(v4_review_signature(source_path($this->root,$entry['_model']))!==$entry['_reviewSignature'])throw new \RuntimeException('Review changed while loading. Please retry.');
            return $entry['_v4']['text'];
        }
        $data=file_get_contents(source_path($this->root,$entry['_text']));
        if (hash('sha256',$data)!==$entry['textSha256']) throw new \RuntimeException('Page changed while loading. Please retry.');
        return $data;
    }
}

function public_entry(array $entry): array {
    foreach (array_keys($entry) as $key) if (strpos($key,'_')===0) unset($entry[$key]);
    return $entry;
}

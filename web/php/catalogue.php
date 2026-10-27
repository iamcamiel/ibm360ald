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
    private ?string $graphGeneration = null;
    private array $metadataCounters = ['lookups'=>0,'strictModelDecodes'=>0,'cacheHits'=>0,'reparses'=>0];
    public function __construct(string $root, ?string $cache = null) {
        $this->root = (string)realpath($root);
        if ($this->root === '') throw new \RuntimeException('Repository is unavailable.');
        $code = ''; $helpers = glob(__DIR__.'/*.py'); sort($helpers, SORT_STRING);
        foreach (array_merge([__FILE__,__DIR__.'/api.php',__DIR__.'/interactions.php',__DIR__.'/strict-json.php'],$helpers) as $file) $code .= $file . ':' . hash_file('sha256',$file) . "\n";
        $this->engine = hash('sha256', $code . (is_file(v4_renderer_path())?(@hash_file('sha256',v4_renderer_path())?:'renderer-unavailable'):'renderer-unavailable'));
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
        return [$relative, $s['mtime'], $s['ctime'], $s['size'], hash_file('sha256',$p)];
    }
    public function metadataStats(): array { return $this->metadataCounters; }
    private function validMetadata(array $value): bool {
        if (array_keys($value)!==['schema','functional','page','title','type','reviewRef','reviewStatus','legacyApproved']) return false;
        foreach (['schema','page','title','type','reviewRef'] as $key) if ($value[$key]!==null&&!is_string($value[$key])) return false;
        if (!is_bool($value['functional'])||!is_bool($value['legacyApproved'])||!is_string($value['reviewStatus'])) return false;
        if ($value['functional']!==($value['schema']===V4_SCHEMA)||($value['schema']!==null&&$value['schema']!==V4_SCHEMA)) return false;
        if (!$value['functional']&&($value['reviewRef']!==null||$value['reviewStatus']!=='unreviewed')) return false;
        if ($value['functional']&&$value['legacyApproved']) return false;
        return $value['reviewRef']===null||$this->safeReviewRef($value['reviewRef']);
    }
    private function safeReviewRef(string $ref): bool {
        return preg_match('~^(?!/)(?!.*(?:^|/)\.{1,2}(?:/|$))[^\\\\:\x00]+$~D',$ref)===1;
    }
    private function sourceMetadata(string $path, ?string $expectedSha = null): array {
        $this->metadataCounters['lookups']++;
        $bytes=file_get_contents($path);
        if ($bytes===false) throw new \RuntimeException('Source model is unavailable.');
        $sha=hash('sha256',$bytes);$schema='aldbrowser-source-metadata-v1';
        if ($expectedSha!==null&&$sha!==$expectedSha) throw new \RuntimeException('Source model changed while reading metadata. Retry.');
        $key='source-metadata-'.hash('sha256',json_bytes([$path,$sha]));
        $cachePath=$this->cache.'/'.hash('sha256',$this->engine.$key).'.json';
        clearstatcache(true,$cachePath);
        // Small derived records share the existing private-cache trust boundary.
        // This digest detects corruption, not deliberate forgery by its owner.
        if (is_file($cachePath)&&filesize($cachePath)<=65536) {
            try {
                $recordBytes=file_get_contents($cachePath,false,null,0,65537);
                $record=is_string($recordBytes)&&strlen($recordBytes)<=65536?strict_json_decode($recordBytes,true):null;
                if (is_array($record)&&array_keys($record)===['schema','sourcePath','modelSha256','metadata','integritySha256']&&
                    $record['schema']===$schema&&$record['sourcePath']===$path&&$record['modelSha256']===$sha&&
                    is_array($record['metadata'])&&$this->validMetadata($record['metadata'])&&
                    is_string($record['integritySha256'])&&hash_equals(hash('sha256',json_bytes([$schema,$path,$sha,$record['metadata']])),$record['integritySha256'])) {
                    $this->metadataCounters['cacheHits']++;
                    return [$record['metadata'],$sha];
                }
            } catch (\Throwable $error) { /* Reparse authoritative bytes below. */ }
        }
        $this->metadataCounters['reparses']++;
        $this->metadataCounters['strictModelDecodes']++;
        $model=strict_json_decode($bytes,false);
        if (!$model instanceof \stdClass) throw new \RuntimeException('Expected source model object.');
        $modelSchema=$model->{'$schema'}??null;
        if (property_exists($model,'$schema')&&$modelSchema!==V4_SCHEMA) throw new \RuntimeException('Unsupported functional page schema.');
        $functional=$modelSchema===V4_SCHEMA;
        foreach (['page','current_extensions','review'] as $field) if (isset($model->$field)&&!$model->$field instanceof \stdClass) throw new \RuntimeException('Invalid source model header.');
        $page=$model->page->page??null;$title=$model->page->title??$model->current_extensions->title??null;
        if (is_array($title)) {
            foreach ($title as $part) if (!is_string($part)) throw new \RuntimeException('Invalid source model title.');
            $title=implode(' ',$title);
        }
        $metadata=['schema'=>$modelSchema,'functional'=>$functional,'page'=>$page,'title'=>$title,
            'type'=>$model->current_extensions->page_type??null,'reviewRef'=>$functional?($model->review->details??null):null,
            'reviewStatus'=>$functional?($model->review->status??'unreviewed'):'unreviewed','legacyApproved'=>false];
        if (!$this->validMetadata($metadata)) throw new \RuntimeException('Invalid source model metadata.');
        unset($model);
        if (!$functional) {
            $this->metadataCounters['strictModelDecodes']++;
            $metadata['legacyApproved']=approved_content($bytes);
        }
        $record=['schema'=>$schema,'sourcePath'=>$path,'modelSha256'=>$sha,'metadata'=>$metadata,
            'integritySha256'=>hash('sha256',json_bytes([$schema,$path,$sha,$metadata]))];
        if (strlen(json_bytes($record))<=65536) $this->put($key,$record);
        return [$metadata,$sha];
    }
    private function reviewSignature(string $path, ?array $source = null, ?string $expectedSha = null): array {
        [$metadata,$sha]=$source??$this->sourceMetadata($path,$expectedSha);
        if (!$metadata['functional']) return [];
        $ref=$metadata['reviewRef'];
        if ($ref===null) return [$sha,null];
        if (!$this->safeReviewRef($ref)) throw new \RuntimeException('Unsafe review details path.');
        $target=realpath(dirname($path).'/'.$ref);$base=realpath(dirname($path));
        if ($target===false||!is_file($target)||strpos($target,$base.DIRECTORY_SEPARATOR)!==0) throw new \RuntimeException('Review details are missing or outside the page directory.');
        return [$sha,hash_file('sha256',$target)];
    }
    private function catalogueSpecs(): array {
        $statusPath = source_path($this->root, 'notes/Source status.json');
        $status = json_read($statusPath); $specs = []; $signatures = [];
        foreach ($status['records'] as $record) {
            $jp = str_replace('\\', '/', $record['repository']['json']['path']);
            $tp = str_replace('\\', '/', $record['repository']['txt']['path']);
            if (strpos($jp, 'json/') !== 0 || substr($jp, -5) !== '.json' || strpos($tp, 'ALD/') !== 0 || substr($tp, -4) !== '.txt' || isset($specs[hash('sha256',$jp)])) throw new \RuntimeException('Invalid or repeated published page identity.');
            $id = hash('sha256', $jp); $sig = [$this->statKey($jp), $this->statKey($tp), $record['page'], $record['repository']['json']['sha256'], $record['repository']['txt']['sha256']];
            $sig[]=$this->reviewSignature(source_path($this->root,$jp),null,$sig[0][4]);
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
            $sig[]=$jp!==null?$this->reviewSignature(source_path($this->root,$jp),null,$sig[1][4]):null;
            $specs[$id] = ['id'=>$id, 'model'=>$jp, 'text'=>$tp, 'card'=>$m[1], 'variant'=>$m[2] ?? null, 'sig'=>$sig];
            $signatures[] = $sig;
        }
        $signature = hash('sha256', json_bytes([$signatures, hash_file('sha256', $statusPath)]));
        return [$specs,$signature,$statusPath];
    }
    public function catalogue(?string $fresh = null): array {
        return $this->locked('catalogue', function () {
            [$specs,$signature,$statusPath] = $this->catalogueSpecs();
            $cached = $this->get('catalogue');
            if (($cached['signature'] ?? '') === $signature) return $cached;
            unset($cached);
            $entries = [];
            foreach ($specs as $id=>$spec) {
                $meta = $this->get('entry-' . $id);
                if (($meta['sig'] ?? null) !== $spec['sig']) {
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
            // Review-only changes are part of the interaction generation too.
            $revision = hash('sha256', $this->engine . $signature);
            foreach ($entries as &$e) $e['interactionURL'] = 'catalogue.php?interaction='.$e['id'].'&v='.$revision;
            unset($e);
            $default = null; foreach ($entries as $e) if ($e['page']==='AP154' && $e['type']==='ald') { $default=$e; break; }
            $default = $default ?? $entries[0];
            $result = ['schema'=>'aldbrowser-catalogue-v1','signature'=>$signature,'revision'=>$revision,
                'sourceStatusSha256'=>hash_file('sha256',$statusPath),'pageCount'=>count($entries),
                'aldPageCount'=>count($specs)-count(array_filter($specs,static function($s){return isset($s['card']);})),
                'cardPageCount'=>count(array_filter($specs,static function($s){return isset($s['card']);})),
                'defaultPage'=>$default['page'],'defaultPageId'=>$default['id'],'pages'=>$entries,'delivery'=>'php-live-v1'];
            [, $after] = $this->catalogueSpecs();
            if ($after !== $signature) throw new \RuntimeException('Catalogue sources changed while indexing. Retry.');
            $this->put('catalogue',$result); return $result;
        });
    }
    private function entry(array $spec): array {
        $text = file_get_contents(source_path($this->root,$spec['text'])); $rows = lines($text); $sha = hash('sha256',$text);
        $source = $spec['model'] ? $this->sourceMetadata(source_path($this->root,$spec['model']),$spec['sig'][isset($spec['card'])?1:0][4]) : null;
        $metadata=$source[0]??null;$msha=$source[1]??null;
        $functional=$metadata['functional']??false;
        $publishedSha=$sha;
        $fileCode = explode(' ',pathinfo($spec['text'],PATHINFO_FILENAME),2)[0]; $card = $spec['card'] ?? null;
        $page = $card !== null ? pathinfo($spec['text'],PATHINFO_FILENAME) : $spec['record']['page'];
        if($functional&&$metadata['page']!==$page)throw new \RuntimeException('Functional page identity does not match the catalogue.');
        $title = $card !== null ? ($spec['variant']!==null ? 'Symbol variant '.$spec['variant'] : 'Canonical pinout') :
            ($metadata['title'] ?? (explode(' ',pathinfo($spec['text'],PATHINFO_FILENAME),2)[1] ?? pathinfo($spec['text'],PATHINFO_FILENAME)));
        if(is_array($title))$title=implode(' ',$title);
        $subpage = null; if ($card===null && preg_match('/^'.preg_quote($page,'/').'-(\d+)$/D',$fileCode,$m)) $subpage=$m[1];
        $displayTitle = $title;
        if ($subpage!==null && !preg_match('/\bpage\s*0*'.(int)$subpage.'\b/i',$title)) $displayTitle.=' page '.$subpage;
        $parts=explode('/',$spec['text']); $section=$card!==null?'Card ALD':implode('/',array_slice($parts,1,-1));
        $e=['id'=>$spec['id'],'page'=>$page,'title'=>$title,'section'=>$section,'type'=>$card!==null?'card-ald':($functional?'ald':($metadata['type']??'ald')),
            'rows'=>count($rows),'columns'=>$rows ? max(array_map(__NAMESPACE__.'\\ulen',$rows)):0,'url'=>source_url($spec['text'],$sha),
            'textSha256'=>$sha,'modelSha256'=>$card!==null?null:$msha,'grid'=>['columnPitch'=>20,'rowPitch'=>30],
            'originalScan'=>null,'txtDownloadName'=>basename($spec['text']),'entryURL'=>'catalogue.php?entry='.$spec['id'],
            '_text'=>$spec['text'],'_model'=>$spec['model']];
        if ($card!==null) { $e['cardType']=$card;$e['variant']=$spec['variant']; }
        else { $e['displayPage']=$subpage!==null?$fileCode:$page;$e['displayTitle']=$displayTitle;$e['subpage']=$subpage; }
        if ($spec['model']) { $e['jsonURL']=source_url($spec['model'],$msha);$e['jsonSha256']=$msha;$e['jsonDownloadName']=$card!==null?$card.'.json':basename($spec['model']); }
        $e['_sourcePairCurrent']=$card!==null || ($spec['record']['repository']['json']['sha256']===$msha && $spec['record']['repository']['txt']['sha256']===$publishedSha);
        if($functional){
            $e['format']='v4';$e['reviewStatus']=$metadata['reviewStatus'];
            $e['reviewBound']=false;$e['renderVerified']=false;$e['nativeViewPending']=true;
            $e['_reviewSignature']=$this->reviewSignature(source_path($this->root,$spec['model']),$source);
        }
        $e['_publishedTextSha256']=$publishedSha;
        $e['userApproved']=!$functional && $card===null && $e['_sourcePairCurrent'] && ($metadata['legacyApproved']??false);
        return $e;
    }
    public function page(string $id, array $catalogue): array {
        foreach ($catalogue['pages'] as $e) if ($e['id']===$id) {
            if (($e['format']??null)!=='v4') return $e;
            return $this->hydrate($e,$catalogue['signature']);
        }
        throw new \OutOfBoundsException('Page is unavailable.');
    }
    private function assertGeneration(string $generation): void {
        [, $current]=$this->catalogueSpecs();
        if ($current!==$generation) throw new \RuntimeException('Catalogue generation changed. Retry.');
    }
    public function assertGraphGeneration(array $catalogue): void {
        $this->assertGeneration($catalogue['signature']);
    }
    private function selectedSignature(array $entry): array {
        $this->document($entry);
        $textHash=hash_file('sha256',source_path($this->root,$entry['_text']));
        if ($textHash!==$entry['_publishedTextSha256']) throw new \RuntimeException('Published text changed while loading. Retry.');
        $review=$this->reviewSignature(source_path($this->root,$entry['_model']),null,$entry['jsonSha256']);
        if ($review!==$entry['_reviewSignature']) throw new \RuntimeException('Review changed while loading. Retry.');
        return [$entry['jsonSha256'],$textHash,$review];
    }
    private function hydrate(array $entry, string $generation): array {
        $sig=$this->selectedSignature($entry);
        $key='native-'.$entry['id'].'-'.hash('sha256',json_bytes([$generation,$sig]));
        return $this->locked($key,function()use($entry,$sig,$key,$generation){
            $this->assertGeneration($generation);
            if ($this->selectedSignature($entry)!==$sig) throw new \RuntimeException('Selected page generation changed. Retry.');
            $cached=$this->get($key);
            $view=$cached['view']??null;
            if ($view===null) {
                $view=native_v4_view(source_path($this->root,$entry['_model']));
                if ($view['modelSha256']!==$entry['jsonSha256'] || $view['page']!==$entry['page'] || $this->selectedSignature($entry)!==$sig) throw new \RuntimeException('Page or review changed while rendering. Retry.');
                $this->put($key,['view'=>$view]);
            }
            if ($view['modelSha256']!==$entry['jsonSha256'] || $view['page']!==$entry['page'] || hash('sha256',$view['text'])!==$view['textSha256']) throw new \RuntimeException('Invalid selected native cache.');
            if ($this->selectedSignature($entry)!==$sig) throw new \RuntimeException('Page changed while loading native view. Retry.');
            $rows=lines($view['text']);$entry['rows']=count($rows);$entry['columns']=$rows?max(array_map(__NAMESPACE__.'\\ulen',$rows)):0;
            $entry['textSha256']=$view['textSha256'];$entry['url']='catalogue.php?text='.$entry['id'].'&v='.$view['textSha256'];
            $entry['reviewStatus']=$view['reviewStatus'];$entry['reviewBound']=$view['reviewBound'];$entry['unresolvedCount']=$view['unresolvedCount'];
            $entry['renderVerified']=true;$entry['nativeViewPending']=false;$entry['userApproved']=false;$entry['_v4']=$view;
            $this->assertGeneration($generation);
            return $entry;
        });
    }
    public function prepareGraphDescriptors(array $catalogue): void {
        $generation=hash('sha256',$this->engine.$catalogue['signature'].$catalogue['revision']);
        $this->locked('graph-descriptors-'.$generation,function()use($catalogue,$generation){
            $this->assertGeneration($catalogue['signature']);
            $expected=[];$pages=[];
            foreach ($catalogue['pages'] as $entry) if (($entry['format']??null)==='v4') {
                $expected[$entry['id']]=[$entry['jsonSha256'],$entry['_reviewSignature'][1]??null,$entry['page']];
                $pages[]=['id'=>$entry['id'],'path'=>source_path($this->root,$entry['_model']),'modelSha256'=>$entry['jsonSha256'],'reviewSha256'=>$entry['_reviewSignature'][1]??null];
            }
            $done=$this->get('graph-complete-'.$generation);
            if (!$expected) {
                $this->assertGeneration($catalogue['signature']);
                $this->put('graph-complete-'.$generation,['generation'=>$generation,'count'=>0]);
                return;
            }
            if (($done['generation']??null)===$generation && ($done['count']??null)===count($expected)) {
                foreach ($expected as $id=>$values) $this->checkedDescriptor($id,$generation,$values);
                $this->assertGeneration($catalogue['signature']);
                return;
            }
            $manifest=tempnam($this->cache,'.gm-');$errors=tempnam($this->cache,'.ge-');
            if ($manifest===false||$errors===false) throw new \RuntimeException('Could not create graph batch files.');
            $process=null;$pipes=[];
            try {
                if (file_put_contents($manifest,json_bytes(['schema'=>'aldbrowser-v4-graph-batch-v1','generation'=>$generation,'pages'=>$pages]))===false) throw new \RuntimeException('Could not write graph batch.');
                unset($pages);
                $python=getenv('ALDBROWSER_PYTHON')?:(PHP_OS_FAMILY==='Windows'?'python':'python3');
                $process=proc_open([$python,'-B','-X','utf8',__DIR__.'/v4_descriptor.py',$manifest,v4_renderer_path()],[0=>['pipe','r'],1=>['pipe','w'],2=>['file',$errors,'w']],$pipes);
                if (!is_resource($process)) throw new \RuntimeException('Could not start graph descriptor batch.');
                fclose($pipes[0]);$seen=[];$complete=false;
                while (($line=fgets($pipes[1]))!==false) {
                    $value=strict_json_decode($line,true);
                    if (!is_array($value)||($value['generation']??null)!==$generation||$complete) throw new \RuntimeException('Invalid graph descriptor framing.');
                    if (($value['schema']??null)==='aldbrowser-v4-graph-complete-v1') {
                        if (($value['count']??null)!==count($expected)||count($seen)!==count($expected)) throw new \RuntimeException('Incomplete graph descriptor batch.');
                        $complete=true;continue;
                    }
                    $id=$value['id']??'';
                    if (!is_string($id)||!isset($expected[$id])||isset($seen[$id])) throw new \RuntimeException('Unexpected graph descriptor page.');
                    $this->validateDescriptor($value,$id,$generation,$expected[$id]);
                    $this->put('graph-descriptor-'.$generation.'-'.$id,$value);$seen[$id]=true;
                }
                fclose($pipes[1]);$code=proc_close($process);$process=null;
                if ($code!==0||!$complete) throw new \RuntimeException('Functional graph descriptor validation failed.');
                $this->assertGeneration($catalogue['signature']);
                $this->put('graph-complete-'.$generation,['generation'=>$generation,'count'=>count($expected)]);
            } finally {
                if (is_resource($process)) { proc_terminate($process);foreach($pipes as $pipe)if(is_resource($pipe))fclose($pipe);proc_close($process); }
                if (is_file($manifest)) unlink($manifest);if(is_file($errors))unlink($errors);
            }
        });
        $this->graphGeneration=$generation;
    }
    private function validateDescriptor(array $value,string $id,string $generation,array $expected): void {
        if (($value['schema']??null)!=='aldbrowser-v4-graph-descriptor-v1'||($value['id']??null)!==$id||($value['generation']??null)!==$generation||($value['modelSha256']??null)!==$expected[0]||($value['reviewSha256']??null)!==$expected[1]||($value['page']??null)!==$expected[2]||!is_array($value['outputs']??null)||!is_array($value['nets']??null)) throw new \RuntimeException('Invalid graph descriptor identity.');
        foreach ($value['outputs'] as $output) if (!is_string($output)) throw new \RuntimeException('Invalid graph output identity.');
        foreach ($value['nets'] as $net) {
            if (!is_array($net)||!is_string($net['id']??null)||($net['label']??null)!==$net['id']||!is_array($net['sourceReferences']??null)) throw new \RuntimeException('Invalid graph net descriptor.');
            $seen=[];foreach($net['sourceReferences'] as $reference) {
                if(!is_string($reference)||isset($seen[$reference]))throw new \RuntimeException('Invalid graph source reference.');
                $seen[$reference]=true;
            }
        }
    }
    private function checkedDescriptor(string $id,string $generation,array $expected): array {
        $value=$this->get('graph-descriptor-'.$generation.'-'.$id);
        if ($value===null) throw new \RuntimeException('Graph descriptor cache is incomplete.');
        $this->validateDescriptor($value,$id,$generation,$expected);return $value;
    }
    public function graphDescriptor(array $entry): array {
        if ($this->graphGeneration===null) throw new \RuntimeException('Graph descriptors have not been prepared.');
        return $this->checkedDescriptor($entry['id'],$this->graphGeneration,[$entry['jsonSha256'],$entry['_reviewSignature'][1]??null,$entry['page']]);
    }
    public function document(array $entry): array {
        if (!$entry['_model']) return [];
        $p=source_path($this->root,$entry['_model']);$data=file_get_contents($p);
        if (hash('sha256',$data)!==$entry['jsonSha256']) throw new \RuntimeException('Page changed while loading. Please retry.');
        return strict_json_decode($data,true);
    }
    public function text(array $entry): string {
        if(isset($entry['_v4'])){
            $this->selectedSignature($entry);
            if($this->reviewSignature(source_path($this->root,$entry['_model']),null,$entry['jsonSha256'])!==$entry['_reviewSignature'])throw new \RuntimeException('Review changed while loading. Please retry.');
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

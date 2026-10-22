<?php
declare(strict_types=1);
namespace ALDbrowser;

function raw_model(array $model): array {
    if (($model['schema']??'')!=='ibm360-ald-page-v2') return $model['current_extensions']??[];
    $raw=$model['current_extensions'];unset($raw['text_layout'],$raw['printed_labels']);
    foreach (['objects','nets','junctions'] as $section) foreach ($model[$section]??[] as $record) {
        $form=$record['source_form'];$container=$form['container'];$ordinal=$form['ordinal'];
        if ($form['value_type']!=='object') $value=$record['current_value'];
        elseif ($section==='objects') {
            $value=array_merge($record['source_literals'],$record['geometry'],$record['source_group_fields'],$record['current_extensions']);
            $terminals=[];foreach ($record['terminals'] as $t) $terminals[$t['terminal_id']]=$t;
            foreach ($form['terminal_collections'] as $collection) {
                $members=[];
                foreach ($collection['members'] as $member) {
                    $source=isset($member['terminal_id'])?$terminals[$member['terminal_id']]:$record['alias_relationships'][$member['alias_index']];
                    $members[]=$source['source_literals'];
                }
                $value[$collection['field']]=$collection['representation']==='array'?$members:$members[0];
            }
        } else {
            $value=$record['source_literals'];
            foreach (['routes','junctions','unresolved_current_claims'] as $kind) foreach ($record[$kind] as $v) $value[$v['kind']]=$v['value'];
            $value=array_merge($value,$record['extensions']);
        }
        $raw[$container][$ordinal]=$value;
    }
    foreach ($model['source_containers'] as $name=>$form) if ($form['projected']) {
        $values=$raw[$name]??[];ksort($values);$raw[$name]=array_values($values);
    }
    return $raw;
}
function pin($value): ?string {
    preg_match_all('/[A-Z]\d{2}/',(string)$value,$m);return count($m[0])===1?$m[0][0]:null;
}
function reference($v): ?string {
    if (is_string($v)) return trim($v);
    if (!is_array($v)) return null;
    if (($v['object_identifier']??null)==='external') return $v['port_reference_text']??null;
    if (!empty($v['page'])&&!empty($v['designation'])) return $v['page'].$v['designation'];
    foreach (['reference','text','value','raw'] as $k) { $found=reference($v[$k]??null);if ($found) return $found; }
    return null;
}
function references($v): array {
    if (is_array($v) && array_keys($v)===range(0,count($v)-1)) { $out=[];foreach ($v as $q) $out=array_merge($out,references($q));return $out; }
    $found=reference($v);return $found?[$found]:[];
}
function page_reference(string $s): ?array {
    return preg_match('/^(?:external[.:])?([A-Z]{2}\d{3})(?:[.-]?([A-Z]{2,3})(\d+))?$/D',$s,$m)?$m:null;
}
function output_designations(array $node, ?string $terminal): array {
    $pins=array_values(array_filter($node['pins']??[],static function($p){return is_array($p)&&($p['side']??null)==='output';}));
    if ($terminal!==null && $terminal!=='output' && $terminal!=='out') {
        $physical=pin($terminal);$pins=array_values(array_filter($pins,static function($p)use($physical){return $physical!==null&&pin($p['pin']??null)===$physical;}));
    } elseif ($terminal==='output'||$terminal==='out') $pins=array_values(array_filter($pins,static function($p){return !pin($p['pin']??null);}));
    if (($terminal===null||$terminal==='output'||$terminal==='out')&&count($pins)!==1) return [];
    $out=[];foreach ($pins as $p) if (isset($node['row'],$p['row'])&&is_int($node['row'])&&is_int($p['row'])&&$p['row']>=$node['row']) $out[]=$p['row']-$node['row']+1;
    return array_values(array_unique($out));
}
function gate_box(array $rows,array $node): ?array {
    $x=$node['column']??null;$y=$node['row']??null;
    if (!is_int($x)||!is_int($y)||$x<0||!isset($rows[$y])||!preg_match('/^┌[─━]+┐/u',usub($rows[$y],$x),$m)) return null;
    $right=$x+ulen($m[0])-1;$id=(string)($node['id']??'');$grid=(string)($node['grid']??'');
    if ($id===''||$grid==='') return null;
    $pattern='/^'.preg_quote(preg_replace('/\s+/u','',$grid),'/').'[─━-]*'.preg_quote($id,'/').'$/uD';
    for ($r=$y+2;$r<min($y+33,count($rows));$r++) {
        if ($r>$y+2&&usub($rows[$r],$x,1)==='┌') break;
        if (in_array(usub($rows[$r],$x,1),['│','|'],true)&&in_array(usub($rows[$r],$right,1),['│','|'],true)&&
            preg_match($pattern,preg_replace('/\s+/u','',usub($rows[$r],$x+1,$right-$x-1)))) return [$x,$y,$right,$r];
    }
    return null;
}
function socket_name($s): string { return preg_replace('/(?<=[0-9])[BT]$/','',strtoupper(trim((string)$s))); }
function site(array $node): array {
    $raw=(string)($node['location']??$node['site']??'');$board=null;$sockets=[];
    if (preg_match('/^(?:02)?([A-Z])-([A-Z]\d)([A-Z]\d+[BT]?)$/D',strtoupper($raw),$m)) { $board='02'.$m[1].'-'.$m[2];$sockets=[$m[3]]; }
    $e=$node['socket_listing_evidence']??[];if (!is_array($e)||isset($e[0])) $e=[];
    $eb=strtoupper((string)($e['board']??''));if ($eb!==''&&strpos($eb,'02')!==0) $eb='02'.$eb;
    if (!$board) $board=$eb?:null;
    if ($board===$eb) $sockets=array_merge($sockets,$e['sockets']??(isset($e['socket'])?[$e['socket']]:[]));
    $sockets=array_values(array_unique(array_map(__NAMESPACE__.'\\socket_name',array_filter($sockets))));sort($sockets,SORT_STRING);
    return [$raw,$board,$sockets];
}
function regex_spans(string $pattern,string $line): array {
    preg_match_all($pattern,$line,$all,PREG_SET_ORDER|PREG_OFFSET_CAPTURE);$out=[];
    foreach ($all as $m) {
        $start=ulen(substr($line,0,$m[0][1]));$end=$start+ulen($m[0][0]);$groups=[];
        foreach (array_slice($m,1) as $v) $groups[]=[$v[0],$v[1]<0?-1:ulen(substr($line,0,$v[1]))];
        $out[]=[$start,$end,$groups,$m[0][0]];
    }
    return $out;
}
function card_portions(array $entry,string $text): array {
    $rows=lines($text);$card=(string)$entry['cardType'];$out=[];
    foreach ($rows as $r=>$line) {
        foreach (regex_spans('/(?<![A-Z0-9])'.preg_quote($card,'/').'([A-Z0-9]{1,3})(?![A-Z0-9])/u',$line) as $match) {
            $candidates=[];
            for ($top=max(0,$r-20);$top<$r;$top++) foreach (regex_spans('/┌[─━]+┐/u',$rows[$top]) as $border) {
                [$left,$end]=$border;$right=$end-1;
                if (!($left<$match[0]&&$match[1]<=$right)) continue;
                $blocked=false;for ($y=$top+1;$y<=$r;$y++) if (in_array(usub($rows[$y],$left,1),['┌','└'],true)) $blocked=true;
                if ($blocked) continue;
                for ($bottom=$r+1;$bottom<min($r+22,count($rows));$bottom++) if (usub($rows[$bottom],$left,$right-$left+1)==='└'.str_repeat('─',$right-$left-1).'┘') { $candidates[]=[$left,$top,$right,$bottom];break; }
            }
            if (count($candidates)===1) $out[]=['portion'=>$match[2][0][0],'cardType'=>$card,'spans'=>[[$r,$match[0],$match[1]]],'box'=>$candidates[0]];
        }
        foreach (regex_spans('/[└┌]R\s+(?:[A-Z0-9]{1,3}\s+)?[UST]\d{2}[A-Z]{2}\s+([A-Z0-9]{2})(?![A-Z0-9])/u',$line) as $m) {
            if (!in_array($m[2][0][0],array_column($out,'portion'),true)) $out[]=['portion'=>$m[2][0][0],'cardType'=>$card,'spans'=>[[$r,$m[0],$m[1]]]];
        }
    }
    return $out;
}
function header_end(array $rows,array $h,array $sockets): int {
    [$top,$left,$right]=$h;
    for ($r=$top+1;$r<count($rows);$r++) {
        $content=usub($rows[$r],$left,$right-$left);
        if (preg_match('/^[│|]?\s{0,2}([A-Z]\d{1,2}[BT]?)(?=\s|[│|])/u',$content,$m)&&!in_array(socket_name($m[1]),$sockets,true)) return $r;
        if (ulen(preg_replace('/[│|\s]/u','',$content))>=12&&preg_match('/^[│|\s─━-]+$/uD',$content)) return $r;
    }
    return count($rows);
}
function socket_payload(array $model,array $rows): array {
    $ext=$model['current_extensions']??[];$records=$ext['sockets']??$ext['records']??[];$out=[];
    foreach (array_values($records) as $ordinal=>$record) {
        if (!is_array($record)) continue;
        $rawSockets=$record['sockets']??(isset($record['socket'])?[$record['socket']]:[]);if (is_string($rawSockets)) $rawSockets=[$rawSockets];
        $sockets=array_values(array_unique(array_map(__NAMESPACE__.'\\socket_name',$rawSockets)));sort($sockets,SORT_STRING);
        $board=strtoupper((string)($record['board']??$ext['board']??''));if ($board!==''&&strpos($board,'02')!==0) $board='02'.$board;
        $card=(string)($record['card_type']??$record['cardType']??'');if (!$sockets||!$board) continue;
        $headers=[];
        foreach ($rawSockets as $socket) foreach ($rows as $r=>$line) foreach (regex_spans('/(?:^|[│|])\s{0,2}('.preg_quote((string)$socket,'/').')(?=\s|[│|]|$)/u',$line) as $m) {
            $tail=usub($line,max($m[0]+1,$m[1]));$offset=strpos($tail,'│');$right=$offset===false?ulen($line):max($m[0]+1,$m[1])+ulen(substr($tail,0,$offset));
            if (isset($record['layout_row'])&&$record['layout_row']!==$r) continue;
            $h=[$r,$m[0],$right,$m[2][0][1],$m[2][0][1]+ulen($m[2][0][0])];$headers[implode(',',$h)]=$h;
        }
        $headers=array_values($headers);
        $hasCard=static function($h)use($rows,$sockets,$card){for($r=$h[0];$r<header_end($rows,$h,$sockets);$r++)if(preg_match('/(?<![A-Z0-9])'.preg_quote($card,'/').'(?![A-Z0-9])/u',usub($rows[$r],$h[1],$h[2]-$h[1])))return true;return false;};
        if (count($headers)>1&&$card!=='') $headers=array_values(array_filter($headers,$hasCard));
        if (count($headers)!==1) continue;
        [$top,$left,$right,$c0,$c1]=$headers[0];$bottom=header_end($rows,$headers[0],$sockets);
        if ($card!==''&&!$hasCard($headers[0])) continue;
        $portions=[];
        foreach ($record['references']??[] as $ref) {
            $page=$ref['ALD_page']??$ref['page']??null;$values=$ref['printed_portions']??$ref['portions']??[];
            if (is_string($values)) $values=preg_split('/\s+/',trim($values));if (!is_string($page)||!is_array($values)) continue;
            $starts=[];for($r=$top;$r<$bottom;$r++)if(preg_match('/(?<![A-Z0-9])'.preg_quote($page,'/').'(?![A-Z0-9])/u',usub($rows[$r],$left,$right-$left)))$starts[]=$r;
            if(count($starts)>1&&$values)$starts=array_values(array_filter($starts,static function($r)use($rows,$left,$right,$values){return preg_match('/(?<![A-Z0-9])'.preg_quote((string)$values[0],'/').'(?![A-Z0-9])/u',usub($rows[$r],$left,$right-$left));}));
            if(isset($ref['layout_row']))$starts=array_values(array_filter($starts,static function($r)use($ref){return$r===$ref['layout_row'];}));
            if(count($starts)!==1)continue;$first=$starts[0];$candidates=[$first];
            for($r=$first+1;$r<$bottom;$r++){
                $content=trim(usub($rows[$r],$left+1,$right-$left-1));
                if(!$content||!preg_match('/^[A-Z0-9]{1,3}(?:\s+[A-Z0-9]{1,3})*$/D',$content)||array_diff(preg_split('/\s+/',$content),array_map('strval',$values)))break;
                $candidates[]=$r;
            }
            foreach($values as $v){$spans=[];foreach($candidates as $r)foreach(regex_spans('/(?<![A-Z0-9])'.preg_quote((string)$v,'/').'(?![A-Z0-9])/u',usub($rows[$r],$left,$right-$left))as$m)$spans[]=[$r,$left+$m[0],$left+$m[1]];
                if($spans)$portions[]=['portion'=>(string)$v,'page'=>$page,'spans'=>$spans];}
        }
        $item=['id'=>'socket-'.$ordinal,'label'=>$board.' '.implode('/',$sockets),'board'=>$board,'sockets'=>$sockets,'cardType'=>$card,'spans'=>[[$top,$c0,$c1]]];
        if($portions)$item['portions']=$portions;$out[]=$item;
    }
    return $out;
}

function graph_key(string $pageId,string $net): string { return $pageId.'|'.$net; }
function graph_find(array &$parent,string $k): string {
    if (!isset($parent[$k])) $parent[$k]=$k;
    $p=$parent[$k];if ($p!==$k) $parent[$k]=graph_find($parent,$p);return $parent[$k];
}
function ensure_graph(Store $store,array $catalogue): void {
    $revision=$catalogue['revision'];if ($store->get('graph-ready-'.$revision)) return;
    $store->locked('graph-'.$revision,function()use($store,$catalogue,$revision){
        if($store->get('graph-ready-'.$revision))return;
        $outputs=[];$pending=[];$labels=[];$pageCodes=[];
        foreach($catalogue['pages']as$entry){
            $pageCodes[$entry['id']]=$entry['displayPage']??$entry['page'];if($entry['type']!=='ald')continue;
            $raw=raw_model($store->document($entry));if(empty($raw['nodes'])&&empty($raw['wire_paths']))continue;
            $nodes=[];foreach($raw['nodes']??[]as$n)if(is_array($n))$nodes[(string)($n['id']??'')]=$n;
            foreach($raw['nets']??[]as$i=>$record){
                if(!is_array($record))continue;$net=(string)($record['id']??$record['net_id']??'net-'.$i);$key=graph_key($entry['id'],$net);
                $driver=reference($record['driver']??null);if(!$driver)continue;
                if(page_reference($driver)){$pending[$key]=$driver;$labels[$key]=(string)($record['label']??$record['name']??$net);continue;}
                $local=explode('.',$driver,2);if(!isset($nodes[$local[0]]))continue;
                foreach(output_designations($nodes[$local[0]],$local[1]??null)as$d){$ref=$entry['page'].'.'.$local[0].'.'.$d;$outputs[$ref][$key]=true;$labels[$key]=(string)($record['label']??$record['name']??$net);}
            }
            unset($raw,$nodes);
        }
        $parent=[];$roots=[];$unresolved=[];
        foreach($pending as$key=>$ref){$m=page_reference($ref);$candidates=isset($m[2])?array_keys($outputs[$m[1].'.'.$m[2].'.'.(int)$m[3]]??[]):[];
            if(count($candidates)===1){$src=$candidates[0];$a=graph_find($parent,$src);$b=graph_find($parent,$key);if($a!==$b)$parent[$b]=$a;$roots[$src]=true;}
            else{$id=substr($key,0,64);$unresolved[$id][substr($key,65)]=$ref;}
        }
        unset($outputs,$pending);$components=[];foreach(array_keys($parent)as$key)$components[graph_find($parent,$key)][]=$key;
        $byPage=[];
        foreach($components as$members){sort($members,SORT_STRING);$items=[];foreach($members as$key){$id=substr($key,0,64);$net=substr($key,65);$items[]=['pageId'=>$id,'id'=>$net,'label'=>$pageCodes[$id].' · '.$labels[$key],'direction'=>isset($roots[$key])?'source':'destination'];}
            $token=hash('sha256',json_bytes($items));$store->put('component-'.$revision.'-'.$token,['items'=>$items]);foreach($members as$key)$byPage[substr($key,0,64)][substr($key,65)]=$token;
        }
        foreach($catalogue['pages']as$e)if($e['type']==='ald')$store->put('graph-page-'.$revision.'-'.$e['id'],['components'=>$byPage[$e['id']]??[],'unresolved'=>$unresolved[$e['id']]??[]]);
        $store->put('graph-ready-'.$revision,['ready'=>true]);
    });
}

function ensure_sockets(Store $store,array $catalogue): array {
    $key='socket-index-'.$catalogue['revision'];$cached=$store->get($key);if($cached!==null)return$cached;
    return $store->locked($key,function()use($store,$catalogue,$key){
        $cached=$store->get($key);if($cached!==null)return$cached;$index=[];
        foreach($catalogue['pages']as$e)if($e['type']==='socket-listing')foreach(socket_payload($store->document($e),lines($store->text($e)))as$item)foreach($item['sockets']as$s)$index[$item['board'].'|'.$s.'|'.$item['cardType']][]=[$e['id'],$item];
        $store->put($key,$index);return$index;
    });
}
function basic_blocks(Store $store,array $entry): array {
    $raw=raw_model($store->document($entry));$rows=lines($store->text($entry));$blocks=[];
    foreach($raw['nodes']??[]as$n){if(!is_array($n))continue;$box=gate_box($rows,$n);if($box===null)continue;[$loc,$board,$sockets]=site($n);
        $blocks[]=['id'=>(string)$n['id'],'label'=>(string)$n['id'].' · '.(string)($n['function']??''),'cardType'=>(string)($n['card_type']??''),'portion'=>(string)($n['portion']??''),'site'=>$loc,'box'=>$box,'_board'=>$board,'_sockets'=>$sockets];}
    return$blocks;
}
function interactions(Store $store,array $entry,array $catalogue): array {
    if (!$entry['_sourcePairCurrent']) throw new \RuntimeException('The page JSON/text publication is incomplete. Retry after both files and Source status are published.');
    $key='payload-'.$catalogue['revision'].'-'.$entry['id'];$cached=$store->get($key);if($cached!==null)return$cached;
    $payload=['schema'=>'aldbrowser-interactions-v1','textSha256'=>$entry['textSha256']];$byId=[];$pages=[];$cards=[];
    foreach($catalogue['pages']as$e){$byId[$e['id']]=$e;if($e['type']==='card-ald'){if($e['variant']===null)$cards[$e['cardType']]=$e;}else$pages[$e['page']][]=$e['id'];}
    if($entry['type']==='card-ald'){$portions=card_portions($entry,$store->text($entry));if($portions)$payload['portions']=$portions;}
    elseif($entry['type']==='socket-listing'){
        $items=socket_payload($store->document($entry),lines($store->text($entry)));$candidatePages=[];
        foreach($items as$item)foreach($item['portions']??[]as$p)foreach($pages[$p['page']]??[]as$id)if($byId[$id]['type']==='ald')$candidatePages[$id]=true;
        foreach(array_keys($candidatePages)as$id)foreach(basic_blocks($store,$byId[$id])as$b)foreach($items as&$item){
            if($b['_board']!==$item['board']||$b['cardType']!==$item['cardType']||!array_intersect($b['_sockets'],$item['sockets']))continue;
            foreach($item['portions']??[]as$p)if($p['portion']===$b['portion']&&$p['page']===$byId[$id]['page'])$item['links'][]=['pageId'=>$id,'selection'=>['kind'=>'block','id'=>$b['id']],'label'=>$p['page'].' · '.$p['portion']];
        }unset($item);if($items)$payload['sockets']=$items;
    }elseif($entry['type']==='ald'){
        $raw=raw_model($store->document($entry));if(empty($raw['nodes'])&&empty($raw['wire_paths'])){$store->put($key,$payload);return$payload;}
        ensure_graph($store,$catalogue);$graph=$store->get('graph-page-'.$catalogue['revision'].'-'.$entry['id']);$nets=[];$dest=[];
        foreach($raw['nets']??[]as$i=>$record){if(!is_array($record))continue;$literal=(string)($record['id']??$record['net_id']??'net-'.$i);
            if(!isset($nets[$literal]))$nets[$literal]=['id'=>$literal,'label'=>(string)($record['label']??$record['name']??$literal),'segments'=>[]];
            foreach(array_merge(references($record['external']??null),references($record['targets']??null))as$ref){$m=page_reference($ref);if($m)$dest[$literal][$m[1]]=true;}
        }
        foreach($raw['wire_paths']??[]as$i=>$path){if(!is_array($path)||($path['net']??'')==='title')continue;$literal=(string)($path['net']??'route-'.$i);
            if(!isset($nets[$literal]))$nets[$literal]=['id'=>$literal,'label'=>$literal,'segments'=>[]];$points=$path['points']??[];
            for($j=1;$j<count($points);$j++){[$a,$b]=[$points[$j-1],$points[$j]];if(count($a)!==2||count($b)!==2||$a===$b||!is_int($a[0])||!is_int($a[1])||!is_int($b[0])||!is_int($b[1])||($a[0]!==$b[0]&&$a[1]!==$b[1]))continue;$seg=[$a[0],$a[1],$b[0],$b[1]];if(!in_array($seg,$nets[$literal]['segments'],true))$nets[$literal]['segments'][]=$seg;}
        }
        foreach($nets as$literal=>&$net){$links=[];$linked=[];
            if(isset($graph['components'][$literal]))foreach($store->get('component-'.$catalogue['revision'].'-'.$graph['components'][$literal])['items']as$other){
                if($other['pageId']===$entry['id']&&$other['id']===(string)$literal)continue;
                $links[]=['pageId'=>$other['pageId'],'selection'=>['kind'=>'net','id'=>$other['id']],'label'=>$other['label'],'direction'=>$other['direction']];$linked[$byId[$other['pageId']]['page']]=true;
            }
            if(isset($graph['unresolved'][$literal])){$ref=$graph['unresolved'][$literal];$net['notes'][]='Source reference '.$ref.' has no unique published driving net.';$m=page_reference($ref);if($m)$dest[$literal][$m[1]]=true;}
            $targets=array_diff_key($dest[$literal]??[],$linked);ksort($targets,SORT_STRING);
            foreach($targets as$page=>$_){$ids=$pages[$page]??[];if(count($ids)===1)$links[]=['pageId'=>$ids[0],'selection'=>null,'label'=>$page,'direction'=>'destination','note'=>'Explicit page reference; target net is not uniquely located.'];else$net['notes'][]='Referenced page '.$page.' is unavailable or ambiguous.';}
            if($links)$net['links']=$links;if(!$net['segments'])unset($net['segments']);
        }unset($net);if($nets)$payload['nets']=array_values($nets);
        $socketIndex=ensure_sockets($store,$catalogue);$blocks=basic_blocks($store,$entry);$cardPortions=[];
        foreach($blocks as&$b){$links=[];$notes=[];$card=$b['cardType'];$portion=$b['portion'];
            if(isset($cards[$card])){$c=$cards[$card];if(!isset($cardPortions[$card]))$cardPortions[$card]=card_portions($c,$store->text($c));
                if(in_array($portion,array_column($cardPortions[$card],'portion'),true))$links[]=['pageId'=>$c['id'],'selection'=>['kind'=>'portion','cardType'=>$card,'portion'=>$portion],'label'=>'Card '.$card.' · '.$portion];
                else$links[]=['pageId'=>$c['id'],'selection'=>null,'label'=>'Card '.$card,'note'=>'Portion is not located in the published card drawing.'];
            }elseif($card!=='')$notes[]='Card ALD '.$card.' is not published.';
            $matches=[];foreach($b['_sockets']as$s)foreach($socketIndex[$b['_board'].'|'.$s.'|'.$card]??[]as$m)$matches[$m[0].'|'.$m[1]['id']]=$m;ksort($matches,SORT_STRING);
            foreach($matches as[$sid,$item])$links[]=['pageId'=>$sid,'selection'=>['kind'=>'socket','id'=>$item['id'],'portion'=>$portion,'page'=>$entry['page']],'label'=>($byId[$sid]['displayPage']??$byId[$sid]['page']).' · '.$item['label']];
            if($b['_board']&&!$matches)$notes[]='No exact published socket/card match is located for '.$b['site'].'.';
            unset($b['_board'],$b['_sockets']);if($links)$b['links']=$links;if($notes)$b['notes']=$notes;
        }unset($b);if($blocks)$payload['blocks']=$blocks;
    }
    $store->put($key,$payload);return$payload;
}

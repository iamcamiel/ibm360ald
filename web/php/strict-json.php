<?php
declare(strict_types=1);
namespace ALDbrowser;

/** Reject duplicate keys before a decoded object can hide conflicting facts. */
function strict_json_decode(string $bytes, bool $associative = true) {
    $value=json_decode($bytes,$associative,512,JSON_THROW_ON_ERROR);
    // Request-local successful validations only; never retain decoded values.
    // Native decoding still runs on every call, with the requested value types.
    static $validated=[];
    $digest=hash('sha256',$bytes);
    if(isset($validated[$digest]))return $value;

    // Native decoding above validates grammar, UTF-8 and nesting first.
    // Scan only raw structural boundaries, skipping string bodies without a
    // regex token array or a JIT/backtracking limit that can hide later keys.
    $stack=[];$length=strlen($bytes);$i=0;
    while($i<$length){
        $i+=strcspn($bytes,'"{}[]',$i);
        if($i===$length)break;
        $token=$bytes[$i++];
        if($token==='"'){
            $start=$i-1;
            while(true){
                $i+=strcspn($bytes,"\"\\",$i);
                if($i>=$length)throw new \RuntimeException('Invalid JSON string.');
                if($bytes[$i]==='\\'){$i+=2;continue;}
                $i++;break;
            }
            $after=$i+strspn($bytes," \t\r\n",$i);
            if(($bytes[$after]??null)===':'){
                $key=json_decode(substr($bytes,$start,$i-$start),true,512,JSON_THROW_ON_ERROR);$top=count($stack)-1;
                if($top<0||!$stack[$top]['object'])throw new \RuntimeException('Invalid JSON object.');
                if(array_key_exists($key,$stack[$top]['keys']))throw new \RuntimeException('Duplicate JSON object key.');
                $stack[$top]['keys'][$key]=true;
            }
        }elseif($token==='{')$stack[]=['object'=>true,'keys'=>[]];
        elseif($token==='[')$stack[]=['object'=>false];
        else array_pop($stack);
    }
    $check=function($item)use(&$check):void{
        if(is_float($item)&&!is_finite($item))throw new \RuntimeException('Non-finite JSON number.');
        if(is_array($item)||is_object($item))foreach($item as$child)$check($child);
    };
    $check($value);
    // Bound digest memory; eviction merely requires validation again.
    if(count($validated)>=4096)unset($validated[array_key_first($validated)]);
    $validated[$digest]=true;
    return $value;
}

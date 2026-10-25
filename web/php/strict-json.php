<?php
declare(strict_types=1);
namespace ALDbrowser;

/** Reject duplicate keys before a decoded object can hide conflicting facts. */
function strict_json_decode(string $bytes, bool $associative = true) {
    $value=json_decode($bytes,$associative,512,JSON_THROW_ON_ERROR);
    preg_match_all('/"(?:\\\\.|[^"\\\\])*"|[{}\[\]:,]/s',$bytes,$matches);
    $tokens=$matches[0];$stack=[];
    foreach($tokens as$i=>$token){
        if($token==='{'){$stack[]=['object'=>true,'keys'=>[]];continue;}
        if($token==='['){$stack[]=['object'=>false];continue;}
        if($token==='}'||$token===']'){array_pop($stack);continue;}
        if($token!==''&&$token[0]==='"'&&($tokens[$i+1]??null)===':'){
            $key=json_decode($token,true,512,JSON_THROW_ON_ERROR);$top=count($stack)-1;
            if($top<0||!$stack[$top]['object'])throw new \RuntimeException('Invalid JSON object.');
            if(array_key_exists($key,$stack[$top]['keys']))throw new \RuntimeException('Duplicate JSON object key.');
            $stack[$top]['keys'][$key]=true;
        }
    }
    $check=function($item)use(&$check):void{
        if(is_float($item)&&!is_finite($item))throw new \RuntimeException('Non-finite JSON number.');
        if(is_array($item)||is_object($item))foreach($item as$child)$check($child);
    };
    $check($value);return$value;
}

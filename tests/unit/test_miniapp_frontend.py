"""Run the session bootstrap in JavaScript without Telegram or network."""

import shutil
import subprocess

import pytest


def test_visitor_bootstrap_and_verified_admin_entry():
    if not shutil.which("node"):
        pytest.skip("node required")
    script = r"""
const assert = require('node:assert/strict'), vm = require('node:vm'), fs = require('node:fs');
const source = fs.readFileSync('app/web/storefront/static/session.js', 'utf8');
async function run({authed=false, verified=false, path='/chat', init='', sdk=true,
                    cookie=true, blocked=false, next, storage=false}={}) {
  const calls=[], locations=[], notice={hidden:true,dataset:{error:'error'}};
  const qb={authed,verified};
  const telegram = sdk ? {Telegram:{WebApp:{initData:init,ready(){},expand(){}}}} : {};
  const context={window:{QB:qb, ...telegram},
    location:{pathname:path,search:'',replace:u=>locations.push(u)},
    document:{querySelector:s=>s==='[data-telegram-auth]'?notice
      :next?{dataset:{loginNext:next}}:null},
    AbortController,
    setTimeout:(fn,ms)=>{if(ms===100)setImmediate(fn); return 1;}, clearTimeout(){},
    fetch:async(url, options)=>{calls.push([url,options]);
      const ok=url==='/auth/webapp'?!blocked:url==='/api/cart'?cookie:true;
      return {ok,status:blocked&&url==='/auth/webapp'?403:ok?200:401,json:async()=>({ok})};
    }};
  vm.runInNewContext(source, context); await qb.ready;
  return {calls,locations,notice};
}
(async()=>{
  for(const sdk of [true,false]) {
    const p=await run({sdk}); assert.deepEqual(p.calls.map(x=>x[0]),['/api/session','/api/cart']);
    assert.deepEqual(p.locations,['/chat']);
  }
  let p=await run({init:'signed'});
  assert.equal(p.calls[0][0],'/auth/webapp'); assert.equal(p.calls.length,2);
  assert(!p.calls.some(x=>x[0].includes('signed')));
  p=await run({path:'/login',init:'signed',next:'/operator'});
  assert.deepEqual(p.locations,['/operator']);
  p=await run({path:'/login'}); assert.equal(p.calls.length,0); // No guest admin access.
  p=await run({authed:true,verified:false,path:'/login',init:'signed',next:'/operator'});
  assert.equal(p.calls[0][0],'/auth/webapp');
  p=await run({authed:true}); assert.equal(p.calls.length,0);
  p=await run({cookie:false}); assert.equal(p.locations.length,0); assert(!p.notice.hidden);
  p=await run({blocked:true,init:'signed'});
  assert.equal(p.calls.length,1); assert.equal(p.locations.length,0);
  p=await run({path:'/login',init:'signed',next:'//evil.test'});
  assert.deepEqual(p.locations,['/operator']);
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr

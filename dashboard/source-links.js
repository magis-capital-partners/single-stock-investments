/* Source navigation only. The publication index resolves real files, including private sources. */
(function (global) {
  'use strict';
  let repairs = {};
  const repo = 'magis-capital-partners/single-stock-investments';
  const vault = 'magis-capital-partners/research-vault';
  const prefixes = [['_system/reference/video/library/','videos/library/'],['_system/reference/podcasts/episodes/','podcasts/episodes/'],['_system/reference/superinvestor-letters/','superinvestor-letters/'],['_system/reference/investment-wisdom/','investment-wisdom/'],['_system/reference/sumzero-research/','sumzero-research/'],['_system/reference/vic-research/','vic-research/'],['_system/reference/manager-meetings/','manager-meetings/']];
  const canonical = value => String(value).replace('github.com/GoldmanDrew/single-stock-investments/',`github.com/${repo}/`).replace('raw.githubusercontent.com/GoldmanDrew/single-stock-investments/',`raw.githubusercontent.com/${repo}/`);
  function setIndex(value) {
    repairs = {...(value?.repairs || {})};
    for(const [url,record] of Object.entries({...repairs})) {
      repairs[canonical(url)]=record;
      try { repairs[new URL(canonical(url)).href]=record; } catch (_) {}
    }
  }
  function resolve(value) {
    if (!value) return null;
    const original = String(value);
    if (Object.prototype.hasOwnProperty.call(repairs, original)) return repairs[original].url || null;
    if (/^(#|\/)/.test(original)) return original;
    if (!/^https?:\/\//i.test(original)) return null;
    const normalized=canonical(original);
    if(Object.prototype.hasOwnProperty.call(repairs,normalized))return repairs[normalized].url || null;
    return normalized;
  }
  function reference(ref) {
    if (!ref) return null;
    if (Object.prototype.hasOwnProperty.call(repairs, ref)) return repairs[ref].url || null;
    if (/^https?:\/\//i.test(ref)) return resolve(ref);
    const clean = String(ref).replace(/\\/g,'/').replace(/^\/+/, '');
    const [before, after] = prefixes.find(([from]) => clean.startsWith(from)) || [];
    const path = before ? after + clean.slice(before.length) : clean;
    const [file, fragment] = /#[^#]*\.(pdf|txt|md)$/i.test(path) ? [path,''] : path.split('#',2);
    return resolve(`https://github.com/${before ? vault : repo}/blob/main/${file.split('/').map(encodeURIComponent).join('/')}${fragment ? '#'+encodeURIComponent(fragment):''}`);
  }
  async function load() {
    try {
      const response = await fetch('data/source_links.json',{credentials:'same-origin',cache:'no-store'});
      if (!response.ok || !(response.headers.get('content-type') || '').includes('json')) return;
      const body = await response.json();
      if (body.schema_version === 'source-links.v1') setIndex(body);
    } catch (_) { /* Existing publications remain readable before their next rebuild. */ }
  }
  function apply(root) {
    const anchors=[...(root.matches?.('a[href]')?[root]:[]),...(root.querySelectorAll?.('a[href]')||[])];
    for(const anchor of anchors) {
      const value=anchor.getAttribute('href');
      if(!/^(https?:\/\/(?:github\.com|raw\.githubusercontent\.com)\/|null$|undefined$)/i.test(value||''))continue;
      const destination=resolve(value);
      if(destination) {if(destination!==value)anchor.setAttribute('href',destination);}
      else {
        const label=anchor.ownerDocument.createElement('span');
        label.className='source-unavailable';label.textContent=anchor.textContent+' (Source unavailable)';
        anchor.replaceWith(label);
      }
    }
  }
  function observe(root) {
    if(!root||!global.MutationObserver)return;
    apply(root);
    const observer=new global.MutationObserver(records=>{
      for(const record of records) {
        if(record.type==='attributes')apply(record.target);
        else for(const node of record.addedNodes)if(node.nodeType===1)apply(node);
      }
    });
    observer.observe(root,{childList:true,subtree:true,attributes:true,attributeFilter:['href']});
    return observer;
  }
  global.SourceLinks = {resolve,reference,load,setIndex,apply,observe};
  if (typeof module !== 'undefined') module.exports = global.SourceLinks;
})(typeof window !== 'undefined' ? window : globalThis);

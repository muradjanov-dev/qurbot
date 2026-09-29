/* Throwaway local interactions. No write APIs, storage, or live AI calls. */
(() => {
  'use strict';
  let data = JSON.parse(document.querySelector('#preview-data').textContent);
  let L = data.labels;
  let products = new Map(data.products.map(p => [Number(p.id), {...p}]));
  let rate = minor(data.rate);
  let selectedId = Number(data.products[0].id);
  const cart = new Map([[Number(data.products[0].id), 2], [Number(data.products[1].id), 1]]);
  const messages = [];
  let category = '', availability = 'all', query = '', navigating = false, toastTimer;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const node = (tag, text, cls) => {const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n;};
  function minor(value) {
    const text = String(value).replace(/\s/g, '').replace(',', '.');
    const match = /^(\d+)(?:\.(\d*))?$/.exec(text);
    if (!match) return null;
    return BigInt(match[1]) * 100n + BigInt((match[2] || '').padEnd(2,'0').slice(0,2)) + ((match[2] || '')[2] >= '5' ? 1n : 0n);
  }
  function raw(value) {return `${value / 100n}.${String(value % 100n).padStart(2,'0')}`;}
  function formatted(value, currency = 'UZS') {
    const whole = (value / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    const fraction = String(value % 100n).padStart(2,'0');
    const suffix = currency === 'USD' ? 'USD' : data.lang === 'uz_latn' ? 'so‘m' : data.lang === 'ru' ? 'сум' : 'сўм';
    return `${whole}${currency === 'USD' || fraction !== '00' ? ',' + fraction : ''} ${suffix}`;
  }
  function price(p) {const amount = minor(p.source_price) || 0n; return p.source_currency === 'USD' ? (amount * rate + 50n) / 100n : amount;}
  function dollar(p) {return p.source_currency === 'USD' ? minor(p.source_price) || 0n : (price(p) * 100n + rate / 2n) / rate;}
  function usd(p) {return `${p.source_currency === 'USD' ? '' : '≈ '}${formatted(dollar(p),'USD')}`;}
  function total() {return [...cart].reduce((sum,[id,qty]) => sum + price(products.get(id)) * BigInt(qty), 0n);}
  function toast(text) {const host = $('[data-preview-toast]');host.textContent = text;host.hidden = false;clearTimeout(toastTimer);toastTimer = setTimeout(() => host.hidden = true, 2800);}
  function currentUrl(screen = data.screen, variant = data.variant, lang = data.lang) {
    return (data.paths[screen] || data.paths.dashboard) + '?' + new URLSearchParams({variant,lang});
  }
  async function navigate(url, push = true) {
    if (navigating) return;
    navigating = true;
    try {
      const response = await fetch(url, {cache:'no-store'});
      if (!response.ok) throw new Error(response.status);
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      const next = JSON.parse($('#preview-data',doc).textContent);
      for (const incoming of next.products) {
        const saved = products.get(Number(incoming.id));
        if (saved && !saved.edited) products.set(Number(incoming.id), {...incoming});
      }
      data = next; L = data.labels;
      document.title = doc.title;
      document.body.className = doc.body.className;
      $('#variant-style').href = $('#variant-style',doc).getAttribute('href');
      $('#prototype-view').replaceWith($('#prototype-view',doc));
      $('.preview-toolbar').replaceWith($('.preview-toolbar',doc));
      for (const id of ['preview-editor','preview-rate','preview-info']) $('#'+id).replaceWith($('#'+id,doc));
      if (push) history.pushState({}, '', url);
      query = '';category = '';availability = 'all';
      initDrawers();render();window.scrollTo(0,0);
    } catch (error) {toast(L.demo_only);}
    finally {navigating = false;}
  }
  function cycle(direction) {const keys=['A','B','C'];navigate(currentUrl(data.screen,keys[(keys.indexOf(data.variant)+direction+3)%3]));}
  function fold(text) {
    const letters={а:'a',б:'b',в:'v',г:'g',д:'d',е:'e',ё:'yo',ж:'j',з:'z',и:'i',й:'y',к:'k',л:'l',м:'m',н:'n',о:'o',п:'p',р:'r',с:'s',т:'t',у:'u',ф:'f',х:'x',ц:'ts',ч:'ch',ш:'sh',щ:'sh',ъ:'',ы:'i',ь:'',э:'e',ю:'yu',я:'ya',ў:'o',қ:'q',ғ:'g',ҳ:'h'};
    return String(text).toLocaleLowerCase().replace(/[а-яўқғҳё]/g,c=>letters[c]||c).replace(/[’ʻ‘`']/g,'');
  }
  function filter() {
    $$('[data-product-row]').forEach(row => {
      const name = fold(row.dataset.name || row.textContent);
      row.hidden = Boolean((query && !name.includes(query)) || (category && (row.dataset.category || '').toLocaleLowerCase() !== category) || (availability !== 'all' && String(row.dataset.available) !== String(availability === 'available')));
    });
    $$('[data-category-filter]').forEach(b => b.setAttribute('aria-pressed',String((b.dataset.categoryFilter || '') === category)));
  }
  function refreshProducts() {
    for (const p of products.values()) {
      $$(`[data-product-title="${p.id}"]`).forEach(n => n.textContent = p.name);
      $$(`[data-price-uzs="${p.id}"]`).forEach(n => n.textContent = formatted(price(p)));
      $$(`[data-price-usd="${p.id}"]`).forEach(n => n.textContent = usd(p));
      $$(`[data-product-status="${p.id}"]`).forEach(n => n.textContent = p.available?L.available:L.unavailable);
      $$(`[data-product-row]`).filter(row => row.querySelector(`[data-add-product="${p.id}"],[data-edit-product="${p.id}"],[data-select-product="${p.id}"]`)).forEach(row => {
        row.dataset.name = p.name;row.dataset.category = p.category;row.dataset.available = String(p.available);
        const image = row.querySelector('img');if (image && p.custom_image) image.src = p.custom_image;
        $$(`[data-add-product="${p.id}"]`,row).forEach(b => b.disabled = !p.available);
      });
    }
    $$('[data-rate-value]').forEach(n => n.textContent = formatted(rate));
    $$('[data-cart-count]').forEach(n => n.textContent = String([...cart.values()].reduce((a,b) => a+b,0)));
    $$('[data-cart-total],[data-cart-subtotal]').forEach(n => n.textContent = formatted(total()));
  }
  function initDrawers() {$$('[data-mobile-drawer]').forEach(panel=>{panel.open=!matchMedia('(max-width: 760px)').matches;});}
  function openPane(id) {const panel=document.getElementById(id.replace(/^#/,''));if(panel){if(panel.tagName==='DETAILS')panel.open=true;panel.scrollIntoView({behavior:'smooth',block:'start'});}}
  function selectProduct(id, reveal = false) {
    const p=products.get(Number(id));if(!p)return;selectedId=Number(id);
    $$('[data-selected-name]').forEach(n => n.textContent=p.name);
    $$('[data-selected-image]').forEach(n => {n.src=p.custom_image || p.image_url;n.alt=p.name;});
    $$('[data-selected-price]').forEach(n => n.textContent=formatted(price(p)));
    $$('[data-selected-usd]').forEach(n => n.textContent=usd(p));
    $$('[data-selected-description]').forEach(n => n.textContent=p.description);
    $$('[data-selected-pack]').forEach(n => n.textContent=p.pack_label);
    $$('[data-selected-source]').forEach(n => n.textContent=p.source_currency);
    $$('[data-selected-status]').forEach(n => n.textContent=p.available?L.available:L.unavailable);
    $$('[data-selected-id]').forEach(n => {
      if (n.hasAttribute('data-add-product')) n.dataset.addProduct=String(id);
      if (n.hasAttribute('data-edit-product')) n.dataset.editProduct=String(id);
      n.dataset.selectedId=String(id);
      if(n.tagName==='BUTTON')n.disabled=!p.available;
      if(n.tagName==='INPUT')n.value=String(id);
      if(n.tagName==='SPAN')n.textContent=String(id);
    });
    $$('[data-selected-product]').forEach(n => {n.dataset.name=p.name;n.dataset.category=p.category;});
    $$('[data-select-product]').forEach(n => n.setAttribute('aria-selected', String(Number(n.dataset.selectProduct)===Number(id))));
    if(reveal && matchMedia('(max-width: 760px)').matches)openPane('vc-selected-pane');
  }
  function renderCart() {
    $$('[data-cart-lines]').forEach(host => {
      host.replaceChildren();
      if (!cart.size) {host.append(node('p',L.empty_cart,'preview-cart-empty'));return;}
      for (const [id,qty] of cart) {
        const p=products.get(id), row=node('div',undefined,'preview-cart-line'), image=node('img');
        image.src=p.custom_image || p.image_url;image.alt=p.name;
        const text=node('div');text.append(node('strong',p.name),node('small',`${formatted(price(p))} · ${usd(p)} / ${p.pack_label}`));
        const controls=node('div',undefined,'preview-cart-controls'), amount=node('input');amount.type='number';amount.min='1';amount.max='1000000';amount.value=String(qty);amount.dataset.cartQty=String(id);amount.setAttribute('aria-label',L.quantity);
        const remove=node('button',L.remove);remove.type='button';remove.dataset.cartRemove=String(id);controls.append(amount,remove);text.append(controls);
        row.append(image,text,node('span',formatted(price(p)*BigInt(qty)),'preview-line-total'));host.append(row);
      }
    });
  }
  function renderChat() {
    const host=$('[data-chat-log]');if(!host)return;
    $$('[data-live-chat]',host).forEach(n=>n.remove());
    for(const message of messages){const bubble=node('div',message.text,'preview-chat-bubble'+(message.user?' user':''));bubble.dataset.liveChat='1';
      if(message.product){const actions=node('div',undefined,'preview-chat-suggestions'), button=node('button',L.add_to_cart);button.type='button';button.dataset.addProduct=String(message.product);actions.append(button);bubble.append(actions);}host.append(bubble);}
    host.scrollTop=host.scrollHeight;
  }
  function render() {refreshProducts();renderCart();selectProduct(selectedId);renderChat();filter();}
  function add(id, source) {
    id=Number(id);const p=products.get(id);if(!p || !p.available)return;
    const row=source?.closest('[data-product-row]'), qty=Math.max(1,Math.min(1000000,parseInt($('[data-quantity]',row||document)?.value || '1',10)||1));
    cart.set(id,(cart.get(id)||0)+qty);render();toast(`${p.name} · ${qty} — ${L.cart}`);
  }
  function openEditor(id) {
    const dialog=$('#preview-editor'), form=$('[data-editor-form]');
    const p=products.get(Number(id));form.reset();form.elements.id.value=p?p.id:'new';
    form.elements.name.value=p?.name || '';form.elements.currency.value=p?.source_currency || 'UZS';form.elements.amount.value=p?.source_price || '';
    form.elements.category.value=p?.category || data.products[0].category;form.elements.pack.value=p?.pack_size || '1';form.elements.description.value=p?.description || '';form.elements.available.checked=p?p.available:true;
    $('h2',dialog).textContent=p?L.edit_product:L.new_product;
    editorPreview();dialog.showModal();
  }
  function editorPreview() {
    const form=$('[data-editor-form]'), value=minor(form.elements.amount.value);
    const p={source_currency:form.elements.currency.value,source_price:value===null?'0':raw(value)};
    $('[data-edit-uzs]').textContent=value===null?'—':formatted(price(p));$('[data-edit-usd]').textContent=value===null?'—':usd(p);
  }
  function showInfo(key) {if(key==='settings'){const d=$('#preview-rate');$('[name=rate]',d).value=raw(rate);d.showModal();return;}
    const d=$('#preview-info');$('[data-info-title]').textContent=L[key] || L.design_preview;d.showModal();}
  document.addEventListener('click',event=>{
    const target=event.target.closest('button,a');if(!target)return;
    if(target.matches('[data-open-pane]')){event.preventDefault();return openPane(target.dataset.openPane);}
    if(target.matches('[data-variant]'))return navigate(currentUrl(data.screen,target.dataset.variant));
    if(target.matches('[data-variant-step]'))return cycle(Number(target.dataset.variantStep));
    if(target.matches('[data-preview-reset]'))return location.reload();
    if(target.matches('[data-close-dialog]'))return target.closest('dialog').close();
    if(target.matches('[data-open-rate]'))return showInfo('settings');
    if(target.matches('[data-new-product]'))return openEditor('new');
    if(target.matches('[data-edit-product]'))return openEditor(target.dataset.editProduct);
    if(target.matches('[data-select-product]'))return selectProduct(target.dataset.selectProduct,true);
    if(target.matches('[data-add-product]'))return add(target.dataset.addProduct,target);
    if(target.matches('[data-cart-remove]')){cart.delete(Number(target.dataset.cartRemove));return render();}
    if(target.matches('[data-demo-action]')){event.preventDefault();return toast(L.demo_only);}
    if(target.tagName==='A'){
      const href=target.getAttribute('href') || '';
      if(href.startsWith('#')){event.preventDefault();return showInfo(href.slice(1));}
      const url=new URL(href,location.href);
      if(url.origin===location.origin && Object.values(data.paths).includes(url.pathname)){event.preventDefault();return navigate(url.pathname+url.search);}
    }
  });
  document.addEventListener('click',event=>{const b=event.target.closest('[data-category-filter]');if(b){category=b.dataset.categoryFilter==='all'?'':(b.dataset.categoryFilter||'').toLocaleLowerCase();filter();}});
  document.addEventListener('click',event=>{const b=event.target.closest('[data-availability-filter]');if(b){availability=b.dataset.availabilityFilter;filter();}});
  document.addEventListener('input',event=>{
    if(event.target.matches('[data-product-search]')){query=fold(event.target.value.trim());filter();}
    if(event.target.closest('[data-editor-form]'))editorPreview();
  });
  document.addEventListener('change',event=>{
    const el=event.target;
    if(el.matches('[data-preview-screen]'))navigate(currentUrl(el.value));
    if(el.matches('[data-preview-lang]'))navigate(currentUrl(data.screen,data.variant,el.value));
    if(el.matches('[data-cart-qty]')){cart.set(Number(el.dataset.cartQty),Math.max(1,Math.min(1000000,parseInt(el.value,10)||1)));render();}
    if(el.name==='currency' && el.closest('[data-editor-form]')){$('[data-editor-form]').elements.amount.value='';editorPreview();}
  });
  document.addEventListener('submit',event=>{
    const form=event.target;event.preventDefault();
    if(form.matches('[data-rate-form]')){const value=minor(form.elements.rate.value);if(value===null||value<=0n)return toast(L.rate_required);rate=value;form.closest('dialog').close();render();return toast(L.rate_saved);}
    if(form.matches('[data-editor-form]')){
      const value=minor(form.elements.amount.value);if(value===null||value<=0n)return toast(L.amount_required);
      const id=form.elements.id.value==='new'?Math.max(...products.keys())+1:Number(form.elements.id.value);
      const original=products.get(id) || {...products.values().next().value,id};
      const p={...original,id,name:form.elements.name.value.trim(),source_currency:form.elements.currency.value,source_price:raw(value),category:form.elements.category.value,pack_size:form.elements.pack.value,description:form.elements.description.value,available:form.elements.available.checked,edited:true};
      const file=form.elements.photo.files[0];if(file)p.custom_image=URL.createObjectURL(file);
      const fresh=!products.has(id);products.set(id,p);
      if(fresh){const seed=$('[data-product-row]');if(seed){const clone=seed.cloneNode(true);for(const n of [clone,...clone.querySelectorAll('*')])for(const a of ['data-add-product','data-edit-product','data-select-product','data-product-title','data-price-uzs','data-price-usd','data-product-status'])if(n.hasAttribute(a))n.setAttribute(a,String(id));seed.parentNode.append(clone);}}
      form.closest('dialog').close();render();return toast(L.saved_demo);
    }
    if(form.matches('[data-chat-form]')){
      const input=form.elements.message, text=input.value.trim();if(!text)return;messages.push({text,user:true});input.value='';renderChat();
      const match=[...products.values()].find(p=>p.name.toLocaleLowerCase().includes(text.toLocaleLowerCase()))||products.values().next().value;
      messages.push({text:`${L.chat_demo}\n\n${match.name}\n${formatted(price(match))} · ${usd(match)} / ${match.pack_label}`,user:false,product:match.id});renderChat();return;
    }
    if(form.matches('[data-checkout-form]')){if(!form.reportValidity())return;toast(L.order_demo);return;}
    toast(L.demo_only);
  });
  document.addEventListener('keydown',event=>{if(event.target.closest('input,textarea,select,[contenteditable],dialog'))return;if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();cycle(event.key==='ArrowLeft'?-1:1);}});
  window.addEventListener('popstate',()=>navigate(location.pathname+location.search,false));
  initDrawers();render();
})();

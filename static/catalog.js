// Use DOM text and event handlers for all user-authored metadata.
let CATEGORIES = [];
const selectedSoftware = new Set();
const collapsedCategories = new Set();
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, action) {
  const node = el('button', text, 'btn btn-sm');
  node.type = 'button'; node.onclick = action; return node;
}
function categoryBranch(id) {
  const ids = new Set([id]);
  let changed = true;
  while (changed) {
    changed = false;
    CATEGORIES.forEach(n => { if (ids.has(n.parentId) && !ids.has(n.id)) { ids.add(n.id); changed = true; } });
  }
  return ids;
}
function categoryPath(id) {
  const parts = [], seen = new Set();
  while (id && !seen.has(id)) {
    seen.add(id); const n = CATEGORIES.find(n => n.id === id);
    if (!n) break; parts.unshift(n.name); id = n.parentId;
  }
  return parts.join(' › ') || '未分类';
}
function categorySelect(value, rootLabel = '未分类', exclude = new Set()) {
  const select = el('select');
  select.add(new Option(rootLabel, ''));
  [...CATEGORIES].sort((a,b) => categoryPath(a.id).localeCompare(categoryPath(b.id), 'zh-CN')).forEach(n => {
    if (!exclude.has(n.id)) select.add(new Option(categoryPath(n.id), n.id));
  });
  select.value = value || ''; return select;
}
loadData = async function() {
  const d = await api('/api/software');
  if (!d.success) throw new Error(d.error || '加载失败');
  ALL_DATA = d.data; CATEGORIES = d.categories || [];
  if(typeof updateTransferLimits === "function") updateTransferLimits(d.limits);
  if (currentCat !== 'all' && currentCat !== '' && !CATEGORIES.some(n => n.id === currentCat)) currentCat = 'all';
};
getFiltered = function() {
  const ids = currentCat === 'all' ? null : (currentCat ? categoryBranch(currentCat) : new Set(['']));
  return ALL_DATA.filter(s => (!ids || ids.has(s.categoryId)) &&
    (!searchTerm || [s.name,s.displayName,s.desc,categoryPath(s.categoryId),s.notes,...(s.tags||[]),
      ...Object.entries(s.customFields||{}).flat()].join(' ').toLowerCase().includes(searchTerm)));
};
selectCategory = function(id) { currentCat = id; currentView = 'home'; currentSoftware = null; render(); };
renderCatSelect = function() {};
function renderTree() {
  let layout = document.getElementById('libraryLayout');
  if (!layout) {
    const container = document.getElementById('container');
    layout = el('div', undefined, 'library-layout'); layout.id = 'libraryLayout';
    container.before(layout);
    const aside = el('aside', undefined, 'category-sidebar'); aside.id = 'categoryTree';
    aside.setAttribute('aria-label', '软件分类目录');
    layout.append(aside, container);
    document.querySelector('.cat-bar').hidden = true;
  }
  const side = document.getElementById('categoryTree'); side.replaceChildren(el('h3', '软件目录'));
  function nav(label, id, count) {
    const b = button(label + ' · ' + count, () => selectCategory(id));
    b.classList.add('tree-link');
    if (currentView === 'home' && currentCat === id) { b.classList.add('active'); b.setAttribute('aria-current','true'); }
    return b;
  }
  side.append(nav('全部软件', 'all', ALL_DATA.length));
  function branch(parent, host) {
    CATEGORIES.filter(n => n.parentId === parent).forEach(n => {
      const ids = categoryBranch(n.id), count = ALL_DATA.filter(s => ids.has(s.categoryId)).length;
      const children = CATEGORIES.some(c => c.parentId === n.id);
      if (children) {
        const details = el('details'); details.open = !collapsedCategories.has(n.id);
        const summary = el('summary'); summary.append(nav(n.name,n.id,count)); details.append(summary);
        const sub = el('div',undefined,'tree-children'); branch(n.id,sub); details.append(sub);
        details.ontoggle = () => details.open ? collapsedCategories.delete(n.id) : collapsedCategories.add(n.id);
        host.append(details);
      } else host.append(nav(n.name,n.id,count));
    });
  }
  branch('',side);
  side.append(nav('未分类','',ALL_DATA.filter(s => !s.categoryId).length));
  if (SESSION?.role === 'admin') side.append(button('管理分类与软件',goAdmin));
}
async function saveCatalog(data) {
  try {
    const result = await api('/api/admin/catalog',{method:'POST',body:data});
    if (!result.success) { showToast(result.error || '保存失败'); return false; }
    await loadData(); closeModal(); render(); showToast('已保存'); return true;
  } catch(e) { showToast('操作未完成，请检查网络后重试'); return false; }
}
function modal(title) {
  const overlay = el('div',undefined,'modal-overlay');
  const box = el('form',undefined,'modal catalog-modal'); box.setAttribute('role','dialog');
  box.setAttribute('aria-modal','true'); box.setAttribute('aria-label',title);
  box.append(el('h2',title)); overlay.append(box);
  document.getElementById('modalContainer').replaceChildren(overlay);
  overlay.onclick = e => { if(e.target === overlay) closeModal(); };
  box.addEventListener('keydown',e => {
    if(e.key === 'Escape') closeModal();
    if(e.key === 'Tab') {
      const inputs = [...box.querySelectorAll('input,select,textarea,button')];
      if(e.shiftKey && document.activeElement === inputs[0]) { e.preventDefault(); inputs.at(-1).focus(); }
      else if(!e.shiftKey && document.activeElement === inputs.at(-1)) { e.preventDefault(); inputs[0].focus(); }
    }
  });
  setTimeout(() => box.querySelector('input,select,button')?.focus(),0);
  return box;
}
function field(form,label,node) { node.setAttribute('aria-label',label); const wrap = el('label',undefined,'catalog-field'); wrap.append(el('span',label),node); form.append(wrap); return node; }
function input(value,limit=200) { const node = el('input'); node.value = value || ''; node.maxLength=limit; return node; }
function actions(form,save,label='保存') {
  const row = el('div',undefined,'catalog-actions');
  const submit = button(label,()=>{}); submit.type='submit'; submit.classList.add('btn-primary');
  row.append(button('取消',closeModal),submit); form.append(row);
  form.onsubmit = async e => { e.preventDefault(); submit.disabled=true; try { await save(); } finally { submit.disabled=false; } };
}
function editCategory(node) {
  const form = modal(node ? '编辑分类' : '新建分类');
  const name = field(form,'分类名称',input(node?.name,80)); name.required=true;
  const parent = field(form,'上级分类',categorySelect(node?.parentId,'顶级分类',node ? categoryBranch(node.id) : new Set()));
  actions(form,()=>saveCatalog({action:node?'update':'create',id:node?.id||'',name:name.value,parentId:parent.value}));
}
function deleteCategory(node) {
  const form = modal('删除分类：' + node.name), ids=categoryBranch(node.id);
  const count=ALL_DATA.filter(s=>ids.has(s.categoryId)).length;
  form.append(el('p',`将删除此分类及其子分类（共 ${ids.size} 个），其中 ${count} 个软件将移至下方目标分类。实际文件不会删除。`));
  const target=field(form,'软件移至',categorySelect('','未分类',ids));
  actions(form,()=>saveCatalog({action:'delete',id:node.id,targetId:target.value}),'删除并移动');
}
function editMetadata(sw) {
  const form=modal('编辑软件资料');
  form.append(el('p','原始名称：'+sw.name));
  const name=field(form,'显示名称',input(sw.displayName));
  const category=field(form,'所属分类',categorySelect(sw.categoryId));
  const desc=field(form,'简介',input(sw.desc,5000));
  const tags=field(form,'标签（逗号分隔）',input((sw.tags||[]).join(', '),1800));
  const notes=el('textarea'); notes.value=sw.notes||''; notes.maxLength=5000; field(form,'备注',notes);
  form.append(el('h3','自定义信息'));
  const fields=el('div'); form.append(fields);
  function addField(k='',v='') {
    const row=el('div',undefined,'custom-field-row'), key=input(k,80), value=input(v,2000);
    key.placeholder='字段名，例如许可证'; key.setAttribute('aria-label','字段名');
    value.placeholder='字段内容'; value.setAttribute('aria-label','字段内容');
    row.append(key,value,button('移除',()=>row.remove())); fields.append(row);
  }
  Object.entries(sw.customFields||{}).forEach(([k,v])=>addField(k,v));
  form.append(button('＋ 添加字段',()=>addField()));
  actions(form,()=> {
    const customFields=Object.create(null);
    for(const row of fields.children) {
      const [k,v]=row.querySelectorAll('input'), key=k.value.trim();
      if(!key || Object.hasOwn(customFields,key)) { showToast('字段名不能为空或重复'); return; }
      customFields[key]=v.value;
    }
    return saveCatalog({action:'metadata',names:[sw.name],displayName:name.value,categoryId:category.value,
      desc:desc.value,notes:notes.value,tags:tags.value.split(/[,，]/).map(t=>t.trim()).filter(Boolean),customFields});
  });
}
function renderCatalogManager(container) {
  const panel=el('section',undefined,'admin-section catalog-manager');
  panel.append(el('h3','分类与软件资料'),el('p','创建多级分类，批量归类；软件资料修改后会在重新扫描和重启后保留。'));
  panel.append(button('＋ 新建分类',()=>editCategory()));
  const list=el('div',undefined,'category-management-list');
  CATEGORIES.forEach(n=> {
    const row=el('div',undefined,'catalog-actions'); row.append(el('span',categoryPath(n.id)),button('编辑',()=>editCategory(n)),button('删除',()=>deleteCategory(n))); list.append(row);
  }); panel.append(list);
  const toolbar=el('div',undefined,'catalog-actions'), search=input(''); search.placeholder='搜索软件、标签或备注'; search.setAttribute('aria-label','管理软件搜索');
  const target=categorySelect(''); target.setAttribute('aria-label','批量移动目标分类');
  const move=button('移动所选',async()=> {
    if(!selectedSoftware.size) { showToast('请先选择软件'); return; }
    move.disabled=true;
    try { if(await saveCatalog({action:'move',names:[...selectedSoftware],categoryId:target.value})) { selectedSoftware.clear(); render(); } }
    finally { move.disabled=false; }
  });
  const status=el('span'), rows=el('div');
  let visible=[];
  toolbar.append(search,target,move,button('全选当前结果',()=>{visible.forEach(s=>selectedSoftware.add(s.name));draw();}),button('清空选择',()=>{selectedSoftware.clear();draw();}),status);
  panel.append(toolbar,rows);
  function draw() {
    const q=search.value.trim().toLowerCase(); rows.replaceChildren();
    visible=ALL_DATA.filter(s=>[s.name,s.displayName,s.desc,s.notes,...(s.tags||[])].join(' ').toLowerCase().includes(q));
    status.textContent='已选 '+selectedSoftware.size+' 项';
    visible.forEach(sw=> {
      const row=el('div',undefined,'catalog-software-row'), check=el('input'); check.type='checkbox'; check.checked=selectedSoftware.has(sw.name);
      check.setAttribute('aria-label','选择 '+sw.displayName);
      check.onchange=()=>{check.checked?selectedSoftware.add(sw.name):selectedSoftware.delete(sw.name);status.textContent='已选 '+selectedSoftware.size+' 项';};
      const label=el('div'); label.append(el('strong',sw.displayName),el('small',categoryPath(sw.categoryId)));
      row.append(check,label,button('编辑资料',()=>editMetadata(sw)),button('官网与更新设置',()=>editOfficialSettings(sw))); rows.append(row);
    });
    if(!visible.length) rows.append(el('p','没有匹配的软件'));
  }
  search.oninput=draw; draw(); container.prepend(panel);
}
const originalRenderAdmin = renderAdmin;
renderAdmin = function(container) {
  originalRenderAdmin(container);
  if(SESSION?.role==='admin') renderCatalogManager(container);
};
const originalRender = render;
render = function() {
  originalRender(); renderTree();
  const categoryCount=document.querySelectorAll('.stats .num')[1];
  if(categoryCount) categoryCount.textContent=CATEGORIES.length;
  const totalFiles=ALL_DATA.reduce((n,s)=>n+s.versions.length,0);
  const totalBytes=ALL_DATA.reduce((n,s)=>n+s.versions.reduce((a,v)=>a+v.size,0),0);
  if(typeof bytes==='function') {
    document.querySelectorAll('.stats .num')[2].textContent=bytes(totalBytes);
    document.querySelector('.footer p').textContent='软件库 · 共 '+totalFiles+' 个文件 · 总计 '+bytes(totalBytes);
  }
  if(currentView!=='home') document.getElementById('statCount').textContent=totalFiles;
  const container=document.getElementById('container');
  if(currentView==='home') {
    // Keep identity and display names separate, and avoid inline handlers for file names.
    const groups=Object.create(null); getFiltered().forEach(sw=>(groups[sw.categoryId]??=[]).push(sw));
    const items=Object.keys(groups).sort().flatMap(k=>groups[k]);
    container.querySelectorAll('.card').forEach((card,i)=>{card.removeAttribute('onclick');card.onclick=()=>goVersion(items[i].name);});
  }
  if(currentView==='version') {
    const sw=ALL_DATA.find(s=>s.name===currentSoftware); if(!sw) return;
    const info=el('section',undefined,'admin-section software-info'); info.append(el('h3',sw.displayName),el('p',categoryPath(sw.categoryId)));
    if(sw.tags?.length) info.append(el('p','标签：'+sw.tags.join(' · ')));
    if(sw.notes) info.append(el('p',sw.notes,'software-notes'));
    const dl=el('dl'); Object.entries(sw.customFields||{}).forEach(([k,v])=>dl.append(el('dt',k),el('dd',v))); info.append(dl);
    if(SESSION?.role==='admin') info.append(button('编辑资料',()=>editMetadata(sw)));
    container.append(info);
  }
};

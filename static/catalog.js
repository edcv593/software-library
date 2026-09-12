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
  if (SESSION?.role === 'admin') {
    for(const [key,label] of adminSections) side.append(button(label,()=>openAdminSection(key)));
  }
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
  submit.setAttribute('aria-label',label);
  const icon=el('span');icon.setAttribute('aria-hidden','true');icon.innerHTML=svg('save',16);
  submit.replaceChildren(icon,el('span',label));
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
let adminSection='software';
const adminSections=[['software','软件管理'],['categories','分类管理'],['accounts','用户管理'],['system','系统设置']];
function openAdminSection(key){adminSection=key;goAdmin();window.scrollTo(0,0);}
function renderCatalogManager(container, categoriesOnly=false) {
  const panel=el('section',undefined,'admin-section catalog-manager');
  panel.append(el('h3',categoriesOnly?'分类管理':'软件管理'));
  if(categoriesOnly){
  panel.append(button('＋ 新建分类',()=>editCategory()));
  const list=el('div',undefined,'category-management-list');
  CATEGORIES.forEach(n=> {
    const row=el('div',undefined,'catalog-actions'); row.append(el('span',categoryPath(n.id)),button('编辑',()=>editCategory(n)),button('删除',()=>deleteCategory(n))); list.append(row);
  }); panel.append(list);
    container.append(panel);return;
  }
  const toolbar=el('div',undefined,'catalog-actions'), search=input(''); search.placeholder='搜索软件、标签或备注'; search.setAttribute('aria-label','管理软件搜索');
  const target=categorySelect(''); target.setAttribute('aria-label','批量移动目标分类');
  const move=button('移动所选',async()=> {
    if(!selectedSoftware.size) { showToast('请先选择软件'); return; }
    move.disabled=true;
    try { if(await saveCatalog({action:'move',names:[...selectedSoftware],categoryId:target.value})) { selectedSoftware.clear(); render(); } }
    finally { move.disabled=false; }
  });
  const status=el('span'), rows=el('div'),pager=el('div',undefined,'catalog-actions'),batch=el('div',undefined,'catalog-actions');
  batch.setAttribute('aria-label','批量操作');
  for(const name of selectedSoftware)if(!ALL_DATA.some(s=>s.name===name))selectedSoftware.delete(name);
  function updateSelection(){status.textContent='已选 '+selectedSoftware.size+' 项';batch.hidden=!selectedSoftware.size;}
  let visible=[],page=0;const pageSize=20;
  toolbar.append(search,button('合并建议',showMergeSuggestions),button('全选当前页',()=>{visible.slice(page*pageSize,(page+1)*pageSize).forEach(s=>selectedSoftware.add(s.name));draw();}));
  batch.append(status,target,move,button('合并所选软件',()=>confirmSoftwareMerge([...selectedSoftware])),button('清空选择',()=>{selectedSoftware.clear();draw();}));
  panel.append(toolbar,batch,rows,pager);
  function draw() {
    const q=search.value.trim().toLowerCase(); rows.replaceChildren();
    visible=ALL_DATA.filter(s=>[s.name,s.displayName,s.desc,s.notes,...(s.tags||[])].join(' ').toLowerCase().includes(q));
    updateSelection();
    page=Math.min(page,Math.max(0,Math.ceil(visible.length/pageSize)-1));
    visible.slice(page*pageSize,(page+1)*pageSize).forEach(sw=> {
      const row=el('div',undefined,'catalog-software-row'), check=el('input'); check.type='checkbox'; check.checked=selectedSoftware.has(sw.name);
      check.setAttribute('aria-label','选择 '+sw.displayName);
      check.onchange=()=>{check.checked?selectedSoftware.add(sw.name):selectedSoftware.delete(sw.name);updateSelection();};
      const label=el('div'); label.append(el('strong',sw.displayName),el('small',categoryPath(sw.categoryId)));
      const more=el('details',undefined,'software-more');more.append(el('summary','更多操作'));
      more.append(button('官网与更新设置',()=>editOfficialSettings(sw)),button('版本管理',()=>goVersion(sw.name)));
      row.append(check,label,button('编辑资料',()=>editMetadata(sw)),more); rows.append(row);
    });
    if(!visible.length) rows.append(el('p','没有匹配的软件'));
    const prev=button('上一页',()=>{page--;draw();}),next=button('下一页',()=>{page++;draw();});
    prev.disabled=page===0;next.disabled=(page+1)*pageSize>=visible.length;
    pager.replaceChildren(prev,el('span',`第 ${page+1} / ${Math.max(1,Math.ceil(visible.length/pageSize))} 页 · 共 ${visible.length} 项`),next);
  }
  search.oninput=()=>{page=0;draw();}; draw(); container.append(panel);
}
const originalRenderAdmin = renderAdmin;
renderAdmin = function(container) {
  if(SESSION?.role!=='admin'){originalRenderAdmin(container);return;}
  // Reuse account and system forms while showing only the selected section.
  originalRenderAdmin(container);
  const accounts=container.querySelector('#accountManagement');
  const system=container.querySelector('.admin-section:last-child');
  container.replaceChildren();
  const navigation=el('nav',undefined,'catalog-actions admin-navigation');
  navigation.setAttribute('aria-label','管理功能');
  for(const [key,label] of adminSections){
    const item=button(label,()=>openAdminSection(key));
    item.setAttribute('aria-current',key===adminSection?'page':'false');navigation.append(item);
  }
  container.append(navigation);
  if(adminSection==='accounts')container.append(accounts);
  else if(adminSection==='system')container.append(system);
  else renderCatalogManager(container,adminSection==='categories');
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

async function showMergeSuggestions(){
  const form=modal('软件合并建议'),content=el('div');form.append(el('p','仅根据名称中版本号差异提供建议，不会自动合并。不同产品或版本渠道请保留独立。'),content);
  content.textContent='正在检查…';
  try{
    const r=await api('/api/admin/grouping');if(!r.success)throw Error(r.error||'检查失败');content.replaceChildren();
    for(const group of r.suggestions){const row=el('div',undefined,'traffic-record');row.append(el('strong',group.names.join(' / ')),el('p',`${group.names.length} 个软件 · ${group.files} 个版本文件`),button('核对并合并',()=>confirmSoftwareMerge(group.names)));content.append(row);}
    if(!r.suggestions.length)content.append(el('p','没有发现高匹配度的重复名称。仍可在软件管理中勾选软件，手动合并。'));
  }catch(e){content.textContent=e.message;}
}
function confirmSoftwareMerge(names){
  const items=names.map(n=>ALL_DATA.find(s=>s.name===n));
  if(items.length<2||items.some(s=>!s||!s.versions.length)){showToast('请至少选择两个包含本地版本的软件');return;}
  const form=modal('确认合并软件');form.append(el('p','文件保持原位；保留目标软件的分类、官网、资料和推荐版本。其他软件的资料不会覆盖目标资料，原版本说明保持不变。'));
  const target=el('select');target.setAttribute('aria-label','保留的软件');items.forEach(s=>target.append(new Option(s.displayName||s.name,s.name)));const label=el('label','保留的软件');label.append(target);form.append(label);
  const detail=el('details');detail.append(el('summary',`查看全部 ${items.reduce((n,s)=>n+s.versions.length,0)} 个版本文件`));
  for(const sw of items){detail.append(el('h3',sw.displayName||sw.name));for(const v of sw.versions)detail.append(el('p',v.filename));}form.append(detail);
  actions(form,async()=>{
    const paths=items.filter(s=>s.name!==target.value).flatMap(s=>s.versions.map(v=>v.path));
    const r=await transferApi('/api/admin/versions',{action:'merge',names,target:target.value,paths});
    if(r){selectedSoftware.clear();await loadData();closeModal();render();showToast('已合并，所有版本集中到目标软件');}
  },'确认合并');
}
async function toggleAccount(buttonNode){
  const name=buttonNode.dataset.name,disabled=buttonNode.dataset.disabled==='true';
  const form=modal(disabled?'禁用账号':'启用账号');form.append(el('p',name),el('p',disabled?'禁用后立即退出该账号的所有设备，并停止其下载；软件和历史流量记录保留。':'启用后需要重新登录，原有下载权限保持不变。'));
  actions(form,async()=>{const r=await api('/api/users/'+encodeURIComponent(name),{method:'PUT',body:{disabled}});if(r.success){closeModal();loadUserList();showToast('账号状态已更新');}else showToast(r.error||'更新失败');},disabled?'确认禁用':'确认启用');
}
function passwordForm(name,self){
  const form=modal(self?'修改我的密码':'重置账号密码');form.append(el('p',self?'修改后所有设备需要重新登录。':'账号：'+name+'。重置后该账号所有设备需要重新登录。'));
  let current;
  if(self){current=field(form,'当前密码',input(''));current.type='password';current.autocomplete='current-password';current.required=true;}
  const next=field(form,'新密码',input(''));next.type='password';next.minLength=8;next.maxLength=128;next.autocomplete='new-password';next.required=true;
  const repeat=field(form,'确认新密码',input(''));repeat.type='password';repeat.autocomplete='new-password';repeat.required=true;
  form.append(el('p','新密码需为 8–128 个字符。'));
  actions(form,async()=>{
    if(next.value!==repeat.value){showToast('两次新密码不一致');return;}
    const r=await api(self?'/api/password':'/api/users/'+encodeURIComponent(name),{method:self?'POST':'PUT',body:self?{currentPassword:current.value,password:next.value}:{password:next.value}});
    if(!r.success){showToast(r.error||'保存失败');return;}
    closeModal();
    if(self){delCookie('session');SESSION=null;await loadData();renderHeaderBtns();render();showLogin();}
    else loadUserList();
    showToast('密码已更新，请使用新密码登录');
  },'保存新密码');
}
function changeMyPassword(){passwordForm(SESSION.username,true);}
function resetAccountPassword(name){passwordForm(name,false);}
const accountsOriginalLoad=loadUserList;
loadUserList=async function(){
  await accountsOriginalLoad();
  document.querySelectorAll('#userList .user-row').forEach(row=>{
    const more=el('details',undefined,'account-more');more.append(el('summary','更多操作'));
    row.querySelectorAll('button').forEach(btn=>{if(['禁用账号','启用账号','重置密码','删除'].includes(btn.textContent))more.append(btn);});
    if(more.children.length>1)row.append(more);
  });
};

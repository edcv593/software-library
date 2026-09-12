let TRANSFER_LIMITS = {upload:2147483648,download:8589934592,extensions:[]};
let activeUpload = null;
let queuePollRunning = false;
let queueTasks = [];
const versionSelection = new Set();
const channelLabels = {stable:'稳定版',beta:'测试版',archive:'历史版'};
const taskLabels = {queued:'等待中',indexing:'正在入库',downloading:'下载中',cancelling:'正在取消',completed:'已完成',failed:'失败',cancelled:'已取消'};
function updateTransferLimits(limits) { if(limits) TRANSFER_LIMITS=limits; }
function editOfficialSettings(sw) {
  const form=modal('官网与更新设置');form.append(el('p',sw.displayName||sw.name));
  const official=field(form,'官网地址',input(sw.customOfficial||sw.official,4096));official.type='url';
  const download=field(form,'官方下载直链',input(sw.downloadUrl,4096));download.type='url';
  const visible=el('input');visible.type='checkbox';visible.checked=!!sw.showOfficial;field(form,'在软件详情显示官网入口',visible);
  form.append(el('h3','同步最新版'),el('p','默认下载成功后先等待审核；批准后新版设为推荐，旧版保留为历史版本。普通官网首页不能作为安装包直链。'));
  const source=sw.updateSource||{};
  const kind=el('select');kind.add(new Option('始终指向最新版的下载直链','direct'));kind.add(new Option('GitHub Releases 最新稳定版','github'));kind.add(new Option('UU 远程 Windows 官方最新版','uu'));kind.add(new Option('飞牛 fnOS x86 官方最新版','fnos'));kind.value=source.kind||'direct';field(form,'更新源类型',kind);
  const url=field(form,'最新版下载直链',input(source.url||sw.downloadUrl,4096));url.type='url';
  const filename=field(form,'直链保存文件名（可选）',input(source.filename,200));filename.placeholder='例如 software.exe';
  const repo=field(form,'GitHub 仓库',input(source.repo));repo.placeholder='例如 owner/repo';
  const pattern=field(form,'发布文件匹配规则',input(source.assetPattern));pattern.placeholder='例如 *windows*x64*.exe（必须只匹配一个文件）';
  function toggle(){for(const node of [url,filename])node.disabled=node.parentElement.hidden=kind.value!=='direct';for(const node of [repo,pattern])node.disabled=node.parentElement.hidden=kind.value!=='github';}kind.onchange=toggle;toggle();
  const auto=el('input');auto.type='checkbox';auto.checked=!!source.auto;field(form,'自动检查并下载更新',auto);
  const review=el('input');review.type='checkbox';review.checked=source.requireReview!==false;field(form,'下载完成后需管理员批准发布',review);
  const hours=field(form,'检查间隔（小时）',input(String(source.intervalHours||24)));hours.type='number';hours.min='1';hours.max='720';hours.required=true;
  if(sw.lastUpdateCheck)form.append(el('p','上次检查：'+new Date(sw.lastUpdateCheck*1000).toLocaleString()));
  if(sw.lastUpdateError)form.append(el('p',sw.lastUpdateError,'transfer-error'));
  async function save() {
    const result=await transferApi('/api/admin/software',{name:sw.name,customOfficial:official.value,downloadUrl:download.value,showOfficial:visible.checked,
      updateSource:{kind:kind.value,url:url.value,filename:filename.value,repo:repo.value,assetPattern:pattern.value,auto:auto.checked,requireReview:review.checked,intervalHours:Number(hours.value)}});
    if(result){await loadData();closeModal();render();showToast('官网与更新设置已保存');}return result;
  }
  const sync=button('保存并立即同步',async()=>{
    if(!form.reportValidity())return;sync.disabled=true;
    try{if(await save()){if(await transferApi('/api/admin/update',{name:sw.name}))openDownloadQueue();}}finally{sync.disabled=false;}
  });form.append(sync);actions(form,save);
}
function bytes(value) {
  if(!value) return '0 B';
  const units=['B','KB','MB','GB','TB'],i=Math.min(4,Math.floor(Math.log(value)/Math.log(1024)));
  return (value/1024**i).toFixed(i?1:0)+' '+units[i];
}
function softwareSelect(value='') {
  const select=el('select'); select.add(new Option('自动识别 / 新软件',''));
  ALL_DATA.forEach(sw=>select.add(new Option(sw.displayName||sw.name,sw.name)));
  select.value=value; return select;
}
const oldHeaderTransfers=renderHeaderBtns;
renderHeaderBtns=function() {
  oldHeaderTransfers();
  if(SESSION?.role==='admin') document.getElementById('headerBtns').append(button('下载队列',openDownloadQueue));
};
function openDownloadQueue() {
  if(SESSION?.role!=='admin') return;
  currentView='queue'; currentSoftware=null; render(); pollQueue();
}
async function transferApi(url,body) {
  try {
    const result=await api(url,{method:'POST',body});
    if(!result.success) throw new Error(result.error||'操作失败');
    return result;
  } catch(e) { showToast(e.message||'网络异常，请重试'); return null; }
}
async function saveVersion(body) {
  if(await transferApi('/api/admin/versions',body)) {
    await loadData(); versionSelection.clear(); closeModal(); render(); showToast('版本已更新');
  }
}
function moveVersions(paths,currentName) {
  const form=modal('合并 / 拆分版本');
  form.append(el('p',`已选 ${paths.length} 个文件。选择已有软件名称可合并版本，填写新名称可拆分为独立软件；实际文件保持不变。`));
  const target=field(form,'目标软件名称',input(currentName)); target.required=true;
  const choices=el('datalist'); choices.id='softwareChoices';
  ALL_DATA.forEach(sw=>choices.append(new Option(sw.displayName||sw.name,sw.name)));
  target.setAttribute('list',choices.id);form.append(choices);
  actions(form,()=>saveVersion({paths,software:target.value}),'移动版本');
}
function editVersion(sw,v) {
  const form=modal('编辑版本');form.append(el('p',v.filename));
  const version=field(form,'版本号',input(v.version,80));
  const platform=field(form,'适用系统',input(v.platform,80));platform.placeholder='例如 Windows 11 / macOS / Linux';
  const arch=field(form,'架构',input(v.arch,80));arch.placeholder='例如 x64 / ARM64 / 通用';
  const channel=el('select');Object.entries(channelLabels).forEach(([k,label])=>channel.add(new Option(label,k)));channel.value=v.channel||'stable';field(form,'版本渠道',channel);
  const notes=el('textarea');notes.value=v.notes||'';notes.maxLength=5000;field(form,'更新说明',notes);
  const recommended=el('input');recommended.type='checkbox';recommended.checked=!!v.recommended;field(form,'设为推荐版本（替换同软件的原推荐）',recommended);
  actions(form,()=>saveVersion({paths:[v.path],version:version.value,platform:platform.value,arch:arch.value,channel:channel.value,notes:notes.value,recommended:recommended.checked}));
}
renderVersionPage=function(container) {
  const sw=ALL_DATA.find(s=>s.name===currentSoftware);if(!sw){goHome();return;}
  const panel=el('section',undefined,'admin-section');
  panel.append(button('← 返回软件库',goHome),el('h2',sw.displayName||sw.name),el('p',sw.desc||''));
  const links=el('div',undefined,'catalog-actions');
  for(const [label,url] of [['官网',sw.showOfficial&&(sw.customOfficial||sw.official)],['官方下载地址',sw.downloadUrl]]) {
    if(url && /^https?:\/\//i.test(url)) { const a=el('a',label,'btn btn-sm');a.href=url;a.target='_blank';a.rel='noopener';links.append(a); }
  }
  panel.append(links);
  const admin=SESSION?.role==='admin',count=el('span');
  const toolbar=el('div',undefined,'catalog-actions');
  const search=input('');search.placeholder='搜索版本号、系统、架构、文件名';search.setAttribute('aria-label','筛选版本');
  const sort=el('select');[['recommended','推荐优先'],['newest','日期从新到旧'],['version','版本号从高到低']].forEach(([k,v])=>sort.add(new Option(v,k)));sort.setAttribute('aria-label','版本排序');
  const history=el('input');history.type='checkbox';history.setAttribute('aria-label','显示历史版本');const historyLabel=el('label');historyLabel.append(history,el('span',' 显示历史版本'));
  toolbar.append(search,sort,historyLabel);
  if(admin) toolbar.append(button('全选当前版本',()=>{filtered().forEach(v=>versionSelection.add(v.path));draw();}),
    button('清空选择',()=>{versionSelection.clear();draw();}),button('合并 / 拆分所选',()=>{
      const paths=sw.versions.filter(v=>versionSelection.has(v.path)).map(v=>v.path);
      if(!paths.length){showToast('请先选择版本');return;}moveVersions(paths,sw.name);
    }),button('上传新版本',()=>doUpload(sw.name)),button('官网与更新设置',()=>editOfficialSettings(sw)),count);
  panel.append(toolbar);
  const rows=el('div');panel.append(rows);
  function filtered() {
    const q=search.value.toLowerCase().trim();
    const list=sw.versions.filter(v=>(history.checked||v.channel!=='archive')&&[v.filename,v.version,v.platform,v.arch,v.notes,channelLabels[v.channel]].join(' ').toLowerCase().includes(q));
    return list.sort((a,b)=>sort.value==='newest'?(b.date||'').localeCompare(a.date||''):sort.value==='version'?(b.version||b.filename).localeCompare(a.version||a.filename,undefined,{numeric:true}):Number(b.recommended)-Number(a.recommended));
  }
  function draw() {
    rows.replaceChildren();count.textContent='已选 '+sw.versions.filter(v=>versionSelection.has(v.path)).length+' 项';
    filtered().forEach(v=> {
      const row=el('article',undefined,'version-managed');
      const head=el('div',undefined,'catalog-actions');
      if(admin) {const check=el('input');check.type='checkbox';check.checked=versionSelection.has(v.path);check.setAttribute('aria-label','选择版本 '+v.filename);check.onchange=()=>{check.checked?versionSelection.add(v.path):versionSelection.delete(v.path);count.textContent='已选 '+sw.versions.filter(v=>versionSelection.has(v.path)).length+' 项';};head.append(check);}
      if(v.reviewState==='pending')head.append(el('strong','待审核'));
      if(v.reviewState==='rejected')head.append(el('strong','已拒绝'));
      head.append(el('strong',(v.recommended?'★ 推荐 · ':'')+(v.version||v.filename)));
      const download=el('a','下载','btn btn-download');download.href='/download/'+encodeURIComponent(v.path);download.download=v.filename;head.append(download);
      if(admin&&v.reviewState==='rejected')head.append(button('重新审核',()=>reviewVersion(v,'reopen')));
      if(admin&&v.reviewState==='pending')head.append(button('批准发布',()=>reviewVersion(v,'approve')),button('拒绝发布',()=>reviewVersion(v,'reject')));
      if(admin&&v.channel==='archive'&&!['pending','rejected'].includes(v.reviewState))head.append(button('回退到此版本',()=>reviewVersion(v,'rollback')));
      if(admin) head.append(button('编辑版本',()=>editVersion(sw,v)),button('移动版本',()=>moveVersions([v.path],sw.name)));
      row.append(head,el('div',v.filename,'version-path'),el('p',[channelLabels[v.channel]||'稳定版',v.platform,v.arch,v.sizeText,v.date].filter(Boolean).join(' · ')));
      if(v.notes) row.append(el('p',v.notes,'software-notes'));
      if(v.sha256) {const detail=el('details');detail.append(el('summary','SHA-256 校验值'),el('code',v.sha256));row.append(detail);}
      rows.append(row);
    });
    if(!rows.children.length) rows.append(el('p','没有匹配的版本'));
  }
  search.oninput=draw;sort.onchange=draw;history.onchange=draw;draw();container.replaceChildren(panel);
};
const originalTransferRender=render;
render=function() {
  originalTransferRender();
  if(currentView==='queue') renderQueue();
};
function renderQueue() {
  const container=document.getElementById('container');container.replaceChildren();
  if(SESSION?.role!=='admin'){container.append(el('p','需要管理员权限'));return;}
  const panel=el('section',undefined,'admin-section');
  panel.append(el('h2','下载队列'),el('p','服务器依次下载并入库，可关闭页面。等待中的任务在重启后继续；中断的任务可手动重试。'));
  const form=el('form',undefined,'download-form');
  const url=field(form,'下载直链',input('',4096));url.type='url';url.required=true;url.placeholder='https://…';
  const name=field(form,'所属软件',softwareSelect());
  const filename=field(form,'保存文件名（可选）',input('',220));filename.placeholder='链接不含后缀时填写，例如 setup.exe';
  const submit=button('加入队列',()=>{});submit.type='submit';submit.classList.add('btn-primary');form.append(submit);
  form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;try{if(await transferApi('/api/admin/fetch',{url:url.value,name:name.value,filename:filename.value})){url.value='';filename.value='';showToast('已加入队列');await pollQueue();}}finally{submit.disabled=false;}};
  panel.append(form,el('p','单文件下载上限：'+bytes(TRANSFER_LIMITS.download)));
  const status=el('p');status.id='queueStatus';panel.append(status);
  const rows=el('div');rows.id='downloadQueueRows';panel.append(rows);container.append(panel);drawQueue();
}
function drawQueue() {
  const rows=document.getElementById('downloadQueueRows');if(!rows)return;rows.replaceChildren();
  queueTasks.slice().reverse().forEach(task=> {
    const row=el('article',undefined,'queue-task');
    const head=el('div',undefined,'catalog-actions');head.append(el('strong',task.filename||task.software||'下载任务'),el('span',taskLabels[task.status]||task.status));
    const action=verb=>async()=>{if(await transferApi('/api/admin/downloads',{id:task.id,action:verb}))await pollQueue();};
    if(['queued','downloading'].includes(task.status))head.append(button('取消',action('cancel')));
    if(['failed','cancelled'].includes(task.status))head.append(button('重试',action('retry')));
    if(['failed','cancelled','completed'].includes(task.status))head.append(button('移除记录',action('remove')));
    row.append(head,el('p',task.sourceUrl||task.url,'queue-url'));
    if(task.provider)row.append(el('p',task.provider==='uu'?'已解析 UU 官方下载跳转':'已获取飞牛官方下载签名'));
    if(task.sync)row.append(el('p',task.unchanged?'官网同步：文件内容未变化':'官网同步：按发布审核设置入库，请到版本管理查看'));
    const progress=el('progress');progress.max=task.total||1;
    if(task.total)progress.value=Math.min(task.bytes,task.total);else if(task.status!=='downloading')progress.value=task.status==='completed'?1:0;
    progress.setAttribute('aria-label','下载进度');row.append(progress);
    row.append(el('p',bytes(task.bytes)+(task.total?' / '+bytes(task.total):'')+(task.speed?' · '+bytes(task.speed)+'/秒':'')+' · 尝试 '+task.attempts+' 次'));
    if(task.error)row.append(el('p',task.error,'transfer-error'));
    rows.append(row);
  });
  if(!queueTasks.length)rows.append(el('p','暂无下载任务。在上方粘贴下载直链，或在软件管理中选择“下载留存”。'));
}
async function pollQueue() {
  if(queuePollRunning||SESSION?.role!=='admin')return;
  queuePollRunning=true;
  try {
    const result=await api('/api/admin/downloads');
    if(!result.success)throw new Error(result.error||'加载队列失败');
    const old=queueTasks;queueTasks=result.tasks;
    if(queueTasks.some(t=>t.status==='completed'&&!old.some(o=>o.id===t.id&&o.status==='completed')))await loadData();
    drawQueue();const status=document.getElementById('queueStatus');if(status)status.textContent='每 2 秒自动更新 · 未完成 '+queueTasks.filter(t=>['queued','downloading','cancelling','indexing'].includes(t.status)).length+' 项';
  }catch(e){const status=document.getElementById('queueStatus');if(status)status.textContent='队列加载失败，将自动重试：'+e.message;}
  finally{queuePollRunning=false;}
}
setInterval(()=>{if(currentView==='queue')pollQueue();},2000);
fetchRemoteFile=async function(name) {
  const sw=ALL_DATA.find(s=>s.name===name);if(!sw?.downloadUrl){showToast('请先设置下载直链');return;}
  if(await transferApi('/api/admin/fetch',{url:sw.downloadUrl,name})) {showToast('已加入下载队列');openDownloadQueue();}
};
const oldCloseTransferModal=closeModal;
closeModal=function(){if(activeUpload){showToast('上传进行中，请先取消上传');return;}oldCloseTransferModal();};
doUpload=function(software='') {
  if(!SESSION){showLogin();return;}
  const form=modal('上传安装包 / 新版本');form.onsubmit=e=>e.preventDefault();
  form.append(el('p','支持安装包、镜像、压缩包，可一次选择多个文件。单文件上限 '+bytes(TRANSFER_LIMITS.upload)+'。'));
  const target=SESSION.role==='admin'?field(form,'所属软件',softwareSelect(typeof software==='string'?software:'')):null;
  const picker=el('input');picker.type='file';picker.multiple=true;picker.accept=TRANSFER_LIMITS.extensions.join(',');picker.setAttribute('aria-label','选择上传文件');form.append(picker);
  const drop=el('div','也可将文件拖到这里','upload-area');form.append(drop);
  const rows=el('div');form.append(rows);
  const cancel=button('取消上传',()=>activeUpload?.abort());cancel.hidden=true;
  form.append(cancel,button('关闭',closeModal));
  let running=false,aborted=false;
  async function upload(files) {
    if(running||!files.length)return;running=true;aborted=false;picker.disabled=true;if(target)target.disabled=true;cancel.hidden=false;
    for(const file of files) {
      if(aborted)break;
      const row=el('div',undefined,'upload-result'),label=el('p',file.name),progress=el('progress');progress.max=100;progress.value=0;row.append(label,progress);rows.append(row);
      if(file.size===0||file.size>TRANSFER_LIMITS.upload||!TRANSFER_LIMITS.extensions.some(ext=>file.name.toLowerCase().endsWith(ext))) {
        label.textContent=file.name+'：文件为空、超过上限或格式不支持';label.className='transfer-error';continue;
      }
      await new Promise(resolve=> {
        const xhr=new XMLHttpRequest();activeUpload=xhr;cancel.disabled=false;
        xhr.open('POST','/api/upload');xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.setRequestHeader('X-Session',SESSION.token);xhr.setRequestHeader('X-Filename',encodeURIComponent(file.name));
        if(target?.value)xhr.setRequestHeader('X-Software',encodeURIComponent(target.value));
        xhr.timeout=30*60*1000;
        xhr.upload.onprogress=e=>{if(e.lengthComputable){progress.value=Math.round(e.loaded/e.total*100);label.textContent=file.name+'：'+(progress.value===100?'文件已传输，正在入库…':progress.value+'%');}};
        xhr.upload.onload=()=>{cancel.disabled=true;};
        xhr.onload=async()=> {
          try {
            let r;try{r=JSON.parse(xhr.responseText);}catch{throw new Error(xhr.status===413?'反向代理限制了上传大小，请提高代理上传上限':'服务器响应异常（HTTP '+xhr.status+'），请检查服务或反向代理');}
            if(!r.success)throw new Error(r.error||'上传失败');
            progress.value=100;label.textContent=file.name+'：'+(r.indexed?'上传成功，已入库':'已保存；'+r.warning);
            await loadData();render();
          }catch(e){label.textContent=file.name+'：'+e.message;label.className='transfer-error';}
          finally{activeUpload=null;resolve();}
        };
        xhr.onerror=()=>{label.textContent=file.name+'：连接失败，请检查网络或代理后重新选择文件重试';activeUpload=null;resolve();};
        xhr.ontimeout=()=>{label.textContent=file.name+'：上传超时，请重试';activeUpload=null;resolve();};
        xhr.onabort=()=>{aborted=true;label.textContent=file.name+'：已取消，未继续上传后续文件';activeUpload=null;resolve();};
        xhr.send(file);
      });
    }
    running=false;picker.disabled=false;picker.value='';if(target)target.disabled=false;cancel.hidden=true;
  }
  picker.onchange=()=>upload([...picker.files]);
  drop.ondragover=e=>e.preventDefault();drop.ondrop=e=>{e.preventDefault();upload([...e.dataTransfer.files]);};
};

function reviewVersion(version,action){
  const label={approve:'批准发布',reject:'拒绝发布',rollback:'回退到此版本',reopen:'重新审核'}[action];
  const form=modal(label);form.append(el('p',version.filename),el('p',action==='reopen'?'此版本恢复为待审核，批准前仍不对普通用户发布。':action==='reject'?'该文件保留给管理员查看，不对普通用户发布。':'此版本将设为推荐，其他已发布版本保留为历史版本，不删除文件。'));
  actions(form,()=>saveVersion({action,paths:[version.path]}),label);
}

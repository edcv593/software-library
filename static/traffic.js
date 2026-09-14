adminSections.splice(adminSections.length-1,0,['traffic','下载与流量']);
const renderAdminBeforeTraffic=renderAdmin;
renderAdmin=function(container){
  renderAdminBeforeTraffic(container);
  if(SESSION?.role!=='admin')return;
  if(adminSection==='traffic'){
    container.querySelectorAll('.admin-section').forEach(n=>n.remove());
    const panel=el('section',undefined,'admin-section');container.append(panel);renderTraffic(panel);
  }
  if(adminSection==='system'){
    const backup=el('section',undefined,'admin-section');container.append(backup);
    backup.append(el('h3','管理资料备份'),el('p','导出分类、软件资料、版本设置和当前文件清单，便于整理前存档。'),button('导出资料备份',exportCatalog),button('校验备份与预览差异',previewCatalog));
    const panel=el('section',undefined,'admin-section');container.append(panel);
    panel.append(el('h3','版本与更新'));
    const info=el('p','正在读取版本…');panel.append(info);
    api('/api/version').then(v=>{info.textContent=`版本 ${v.version} · 构建 ${v.revision.slice(0,12)} · ${v.built}`;}).catch(()=>{info.textContent='版本信息读取失败';});
    panel.append(button('检查更新',async()=>{
      info.textContent='正在检查已发布构建…';
      try{const r=await api('/api/admin/check-update');info.textContent=r.success?(r.updateAvailable?'发现更新，发布构建 '+r.latest.slice(0,12)+'。请更新镜像并保留原目录挂载。':'当前已是最新发布构建。'):(r.error||'检查失败');}catch(e){info.textContent='检查失败，请稍后重试';}
    }));
  }
};
function previewCatalog(){
  const form=modal('备份校验与差异预览');form.append(el('p','选择本站导出的 JSON 资料备份（最大 8 MiB）。仅比较资料和扫描清单，不会覆盖配置或移动文件。'));
  const file=el('input');file.type='file';file.accept='.json,application/json';file.required=true;file.setAttribute('aria-label','选择资料备份');form.append(file);
  const result=el('div');result.setAttribute('aria-live','polite');form.append(result);file.onchange=()=>result.replaceChildren();
  actions(form,async()=>{
    const selected=file.files[0];if(!selected)return;if(selected.size>8*1024*1024){result.replaceChildren(el('p','文件超过 8 MiB，请选择较小的资料备份。'));return;}
    file.disabled=true;result.replaceChildren(el('p','正在校验与比较…'));
    try{
      const backup=JSON.parse(await selected.text());const r=await api('/api/admin/catalog-preview',{method:'POST',body:backup});if(!form.isConnected)return;if(!r.success)throw Error(r.error||'校验失败');const p=r.preview;
      result.replaceChildren(el('p',`结构校验通过 · 备份版本 ${p.appVersion} · ${p.createdAt}`),el('p',`备份：${p.counts.categories} 分类 / ${p.counts.software} 软件 / ${p.counts.files} 文件；当前：${p.currentCounts.categories} 分类 / ${p.currentCounts.software} 软件 / ${p.currentCounts.files} 文件。`));
      for(const [key,label] of [['categories','分类资料'],['software','自定义软件设置'],['versions','版本设置'],['files','文件清单（按路径和大小）']]){
        const section=el('section');section.append(el('h3',label));
        for(const [kind,title] of [['backupOnly','仅在备份中'],['currentOnly','仅在当前资料中'],['changed','内容不同']]){const group=p[key][kind],detail=el('details');detail.append(el('summary',`${title}：${group.count} 项`));if(group.count){const list=el('ul');group.items.forEach(item=>list.append(el('li',item)));detail.append(list);if(group.count>group.items.length)detail.append(el('p','仅展示前 100 项'));}section.append(detail);}result.append(section);
      }
      result.append(el('p','文件清单差异仅依据当前扫描结果和文件大小，不代表文件内容校验；资料未被修改。'));
    }catch(e){result.replaceChildren(el('p','校验失败：'+e.message));}finally{file.disabled=false;}
  },'校验并预览');
}
function exportCatalog(){
  const form=modal('导出管理资料');
  form.append(el('p','包含分类树、自定义资料、版本备注、官网下载设置、115 分享链接及访问码和当前文件清单。'),el('p','这是资料存档，不包含安装包、用户账号、SMTP 设置或流量记录。完整站点备份仍需保存 Docker 数据目录和软件目录。当前版本提供导出，尚未提供一键导入恢复。'));
  const status=el('p');status.setAttribute('role','status');form.append(status);
  actions(form,async()=>{
    status.textContent='正在生成备份…';
    try{
      const r=await api('/api/admin/catalog-export');if(!form.isConnected)return;if(!r.success)throw Error(r.error||'导出失败');
      const blob=new Blob([JSON.stringify(r.backup,null,2)],{type:'application/json;charset=utf-8'}),url=URL.createObjectURL(blob),link=el('a');link.href=url;link.download=r.filename;form.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
      const c=r.backup.counts;status.textContent=`备份已生成：${c.categories} 个分类、${c.software} 个软件、${c.files} 个文件记录。请检查浏览器下载列表并妥善保存分享访问码。`;
    }catch(e){status.textContent='导出失败：'+e.message;}
  },'生成并下载');
}
async function renderTraffic(panel){
  panel.replaceChildren(el('h3','下载与流量'));
  const message=el('p','正在读取…');panel.append(message);
  try{
    const data=await api('/api/admin/traffic');if(!data.success)throw Error(data.error||'读取失败');
    message.textContent='仅控制本站文件下载；0 表示不限。每日额度按北京时间零点重置，修改后对后续传输生效。';
    const form=el('form',undefined,'traffic-settings');
    const fields={};
    for(const [key,label,min] of [['speedKiB','总下载速度上限（KiB/s）',0],['dailyMiB','每账号每日额度（MiB）',0],['concurrency','每账号同时下载数',1]]){
      const wrap=el('label',label),field=el('input');field.type='number';field.min=min;field.step=1;field.required=true;field.value=data.settings[key];field.setAttribute('aria-label',label);wrap.append(field);form.append(wrap);fields[key]=field;
    }
    const exempt=el('input');exempt.type='checkbox';exempt.checked=data.settings.adminExempt;const label=el('label');label.append(exempt,el('span','管理员不受限速、每日额度和并发限制'));form.append(label);
    const save=button('保存下载设置',()=>{});save.type='submit';save.classList.add('btn-primary');form.append(save);panel.append(form);
    form.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{
      const body={adminExempt:exempt.checked};for(const [key,field] of Object.entries(fields))body[key]=Number(field.value);
      const r=await api('/api/admin/traffic',{method:'PUT',body});showToast(r.success?'下载设置已保存':r.error||'保存失败');
    }catch(e){showToast('保存失败，请检查网络');}finally{save.disabled=false;}};
    panel.append(el('h3','今日额度用量 · '+data.day+'（北京时间）'));
    for(const row of data.usage)panel.append(el('p',row.username+'：'+bytes(row.bytes)+' · 115 领取 '+(row.cloudClaims||0)+' 次'));
    if(!data.usage.length)panel.append(el('p','今天尚无下载流量'));
    panel.append(button('刷新用量与记录',()=>renderTraffic(panel)),el('h3','最近 100 条下载记录'));
    panel.append(el('p','本地按服务器提交发送的字节计入；115 按领取文件的完整大小计入，并非实际传输量。网络中断或进程异常时，最多一个预留数据块可能未到达客户端，仍计入额度。'));
    const labels={cloud_link:'115 链接领取（按文件大小计额）',completed:'完成',active:'下载中',interrupted:'中断',quota:'额度耗尽',revoked:'权限已撤销'};
    const rows=el('div');panel.append(rows);
    for(const record of data.records){
      const item=el('div',undefined,'traffic-record');item.append(el('strong',record.filename),el('p',`${record.username} · ${bytes(record.bytes)} · ${labels[record.status]||record.status}`),el('small',new Date(record.started*1000).toLocaleString()));rows.append(item);
    }
    if(!data.records.length)rows.append(el('p','暂无下载记录'));
  }catch(e){message.textContent='读取失败：'+e.message;panel.append(button('重试',()=>renderTraffic(panel)));}
}
const headerBeforeTraffic=renderHeaderBtns;
renderHeaderBtns=function(){headerBeforeTraffic();if(SESSION)document.getElementById('headerBtns').append(button('我的额度',showMyTraffic));};
function showMyTraffic(){
  if(!SESSION){showLogin();return;}
  const form=modal('我的下载额度'),content=el('div');form.append(content);
  const refresh=button('刷新额度与记录',load),close=button('关闭',closeModal);form.append(refresh,close);
  const token=SESSION.token;
  async function load(){
    refresh.disabled=true;content.replaceChildren(el('p','正在读取…'));
    try{
      const r=await api('/api/my-traffic');if(!form.isConnected||SESSION?.token!==token)return;if(!r.success)throw Error(r.error||'读取失败');
      content.replaceChildren(el('p',`${r.day} · 每日北京时间零点重置`));
      content.append(el('p',r.downloadAllowed?'账号下载权限：已允许':'账号下载权限：已暂停，请联系管理员',r.downloadAllowed?'':'transfer-error'));
      const amount=el('div',undefined,'quota-summary');amount.append(el('strong',r.remaining===null?'今日额度不限':'今日剩余 '+bytes(r.remaining)),el('p',`今日已用 ${bytes(r.used)}${r.dailyLimit?' / '+bytes(r.dailyLimit):''}`));content.append(amount);
      if(r.dailyLimit){const progress=el('progress');progress.max=r.dailyLimit;progress.value=Math.min(r.used,r.dailyLimit);progress.setAttribute('aria-label','今日额度使用比例');content.append(progress);if(r.remaining===0)content.append(el('p','今日额度已用完，请等待重置或联系管理员。','transfer-error'));}
      content.append(el('p',`当前本站下载 ${r.activeDownloads} 个 · 同时下载上限：${r.concurrencyLimit||'不限'}`));
      content.append(el('p',r.exempt?'管理员额度、并发和限速豁免已生效。':r.settings.speedKiB?`本站总下载速度上限 ${bytes(r.settings.speedKiB*1024)}/秒，由所有受限账号共享。`:'本站未设置总下载速度上限。'));
      content.append(el('p','本地按服务器提交发送的字节计入；115 领取按文件完整大小计额，并非实际下载量。115 下载速度和传输并发不由本站控制。'));
      content.append(el('h3','我的最近 20 条记录'));
      const labels={cloud_link:'115 链接领取',completed:'完成',active:'下载中',interrupted:'中断',quota:'额度耗尽',revoked:'权限已撤销'};
      for(const record of r.records){const row=el('div',undefined,'traffic-record');row.append(el('strong',record.filename),el('p',`${bytes(record.bytes)} · ${labels[record.status]||record.status}`),el('small',new Date(record.started*1000).toLocaleString()));content.append(row);}
      if(!r.records.length)content.append(el('p','暂无下载记录'));
    }catch(e){if(form.isConnected)content.replaceChildren(el('p','读取失败：'+e.message));}
    finally{if(form.isConnected)refresh.disabled=false;}
  }
  load();
}

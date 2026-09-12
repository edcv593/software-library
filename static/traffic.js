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
    panel.append(el('h3','今日用量 · '+data.day+'（北京时间）'));
    for(const row of data.usage)panel.append(el('p',row.username+'：'+bytes(row.bytes)));
    if(!data.usage.length)panel.append(el('p','今天尚无下载流量'));
    panel.append(button('刷新用量与记录',()=>renderTraffic(panel)),el('h3','最近 100 条下载记录'));
    panel.append(el('p','流量按服务器提交发送的字节计入；网络中断或进程异常时，最多一个预留数据块可能未到达客户端，仍计入额度。'));
    const labels={completed:'完成',active:'下载中',interrupted:'中断',quota:'额度耗尽',revoked:'权限已撤销'};
    const rows=el('div');panel.append(rows);
    for(const record of data.records){
      const item=el('div',undefined,'traffic-record');item.append(el('strong',record.filename),el('p',`${record.username} · ${bytes(record.bytes)} · ${labels[record.status]||record.status}`),el('small',new Date(record.started*1000).toLocaleString()));rows.append(item);
    }
    if(!data.records.length)rows.append(el('p','暂无下载记录'));
  }catch(e){message.textContent='读取失败：'+e.message;panel.append(button('重试',()=>renderTraffic(panel)));}
}
const headerBeforeTraffic=renderHeaderBtns;
renderHeaderBtns=function(){headerBeforeTraffic();if(SESSION)document.getElementById('headerBtns').append(button('我的流量',async()=>{
  const form=modal('我的下载额度');const text=el('p','正在读取…');form.append(text);
  try{const r=await api('/api/my-traffic');if(!r.success)throw Error(r.error||'读取失败');const exempt=SESSION.role==='admin'&&r.settings.adminExempt;text.textContent=`${r.day}（北京时间）已用 ${bytes(r.used)}；每日额度：${exempt||!r.settings.dailyMiB?'不限':bytes(r.settings.dailyMiB*1048576)}。`;}catch(e){text.textContent=e.message;}
}));};

// All registration, binding and password recovery use purpose-specific email codes.
const accountView={owner:'',query:'',filter:'all',page:0};
let accountLoadSequence=0;
loadUserList=async function(){
  const host=document.getElementById('userList');if(!host||SESSION?.role!=='admin')return;
  const sequence=++accountLoadSequence,token=SESSION.token;
  if(accountView.owner!==SESSION.username)Object.assign(accountView,{owner:SESSION.username,query:'',filter:'all',page:0});
  host.replaceChildren(el('p','正在读取账号…'));
  try{
    const r=await api('/api/users');
    if(sequence!==accountLoadSequence||!host.isConnected||SESSION?.token!==token||SESSION?.role!=='admin')return;
    if(!r.success)throw Error(r.error||'读取失败');
    const users=r.users.slice().sort((a,b)=>Number(!!b.signupPending)-Number(!!a.signupPending)||a.username.localeCompare(b.username,'zh-CN',{numeric:true}));
    const toolbar=el('div',undefined,'catalog-actions'),search=input(accountView.query,254);search.placeholder='搜索账号或邮箱';search.setAttribute('aria-label','搜索账号或邮箱');
    const filter=el('select');filter.setAttribute('aria-label','账号状态筛选');
    [['all','全部账号'],['pending','待审批'],['disabled','已禁用'],['paused','下载已暂停'],['verified','邮箱已验证'],['unbound','邮箱未验证或未绑定']].forEach(([value,label])=>filter.add(new Option(label,value)));filter.value=accountView.filter;
    toolbar.append(search,filter,button('重置账号筛选',()=>{search.value='';filter.value='all';change();}));
    const summary=el('p',undefined,'browse-summary');summary.setAttribute('role','status');const rows=el('div'),pager=el('nav',undefined,'browse-pagination');pager.setAttribute('aria-label','用户列表分页');
    host.replaceChildren(toolbar,summary,rows,pager);
    function draw(){
      const terms=accountView.query.toLowerCase().trim().split(/\s+/).filter(Boolean);
      const visible=users.filter(u=>{
        const verified=!!u.email&&u.emailVerified;
        const match={all:true,pending:!!u.signupPending,disabled:!!u.disabled&&!u.signupPending,paused:u.role!=='admin'&&!u.canDownload,verified,unbound:!verified}[accountView.filter];
        return match&&terms.every(q=>[u.username,u.email].join(' ').toLowerCase().includes(q));
      });
      const size=20,pages=Math.max(1,Math.ceil(visible.length/size));accountView.page=Math.min(accountView.page,pages-1);const start=accountView.page*size;
      summary.textContent=`共 ${users.length} 个账号 · 待审批 ${users.filter(u=>u.signupPending).length} 个 · 匹配 ${visible.length} 个${visible.length?` · 显示 ${start+1}–${Math.min(start+size,visible.length)}`:''}`;
      rows.replaceChildren();
      visible.slice(start,start+size).forEach(u=>{
        const row=el('div',undefined,'user-row'),info=el('div',undefined,'user-info');
        info.append(el('div',u.username,'user-name'),el('div',u.email?`${u.email} · ${u.emailVerified?'邮箱已验证':'邮箱未验证'}`:'未绑定邮箱','user-role'),el('div',u.created||'','user-role'));
        row.append(info,el('span',u.role==='admin'?'管理员':'普通用户','role-badge '+(u.role==='admin'?'admin':'user')));
        row.append(el('span',u.signupPending?'待审批':u.disabled?'已禁用':'账号正常'));
        const update=(label,body)=>{const b=button(label,async()=>{b.disabled=true;try{const result=await api('/api/users/'+encodeURIComponent(u.username),{method:'PUT',body});if(!result.success){showToast(result.error||'更新失败');return;}showToast('账号已更新');await loadUserList();}catch(e){showToast('更新结果未确认，请刷新账号列表后核对');}finally{b.disabled=false;}});return b;};
        if(u.role!=='admin'){row.append(el('span',u.canDownload?'下载已允许':'下载已暂停'));if(!u.disabled)row.append(update(u.canDownload?'暂停下载':'允许下载',{canDownload:!u.canDownload}));}
        if(u.username!==SESSION.username){
          if(u.signupPending)row.append(update('批准注册',{disabled:false}));
          const more=el('details',undefined,'account-more');more.append(el('summary','更多操作'));
          if(!u.signupPending)more.append(update(u.disabled?'启用账号':'禁用账号',{disabled:!u.disabled}));
          more.append(button('删除账号',()=>delUser(u.username)));row.append(more);
        }
        rows.append(row);
      });
      if(!visible.length)rows.append(el('p','没有匹配的账号，请更换关键词或重置筛选。'));
      pager.replaceChildren();if(pages>1){const prev=button('上一页',()=>{accountView.page--;draw();}),next=button('下一页',()=>{accountView.page++;draw();});prev.disabled=accountView.page===0;next.disabled=accountView.page===pages-1;pager.append(prev,el('span',`第 ${accountView.page+1} / ${pages} 页`),next);}
    }
    function change(){accountView.query=search.value;accountView.filter=filter.value;accountView.page=0;draw();}
    search.oninput=change;filter.onchange=change;draw();
  }catch(e){if(sequence===accountLoadSequence&&host.isConnected&&SESSION?.token===token)host.replaceChildren(el('p','账号列表读取失败：'+e.message),button('重新加载',loadUserList));}
};
const emailSendState=new Map();
function emailFlow(kind,initial=''){
  const title={signup:'邮箱注册',bind:'绑定或更换邮箱',reset:'邮箱重置密码'}[kind];
  const form=modal(title);form.append(el('p',kind==='bind'?'验证码发送到要绑定的新邮箱。':kind==='reset'?'验证码发送到账号已验证的邮箱。重置后所有设备需重新登录。':'完成邮箱验证后按站点规则开通账号；如需管理员审批，注册成功后会提示。下载受每日额度限制。'));
  const email=field(form,'邮箱地址',input(initial,254));email.type='email';email.required=true;email.autocomplete='email';
  const code=field(form,'邮件验证码',input('',6));code.required=true;code.pattern='[0-9]{6}';code.inputMode='numeric';code.autocomplete='one-time-code';
  const feedback=el('p',undefined,'email-feedback');feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');form.append(feedback);
  const tell=(message,error=false)=>{feedback.textContent=message;feedback.classList.toggle('transfer-error',error);};
  const key=()=>JSON.stringify([kind,kind==='bind'?SESSION?.username||'':'',email.value.trim().toLowerCase()]);
  let submitting=false;
  function updateSend(){
    const state=emailSendState.get(key()),remaining=Math.max(0,Math.ceil(((state?.until||0)-Date.now())/1000));
    send.disabled=submitting||!!state?.pending||remaining>0;
    send.textContent=state?.pending?'正在发送…':remaining?`${remaining} 秒后可重发`:state?'重新发送验证码':'发送验证码';
  }
  const send=button('发送验证码',async()=>{
    if(!email.reportValidity())return;
    const requestKey=key(),prior=emailSendState.get(requestKey);if(prior?.pending||prior?.until>Date.now())return;
    const address=email.value.trim().toLowerCase();emailSendState.set(requestKey,{pending:true});updateSend();tell('正在请求发送验证码…');
    try{const endpoint=kind==='signup'?'/api/signup-code':kind==='bind'?'/api/bind-code':'/api/reset-code';const r=await api(endpoint,{method:'POST',body:{email:address}});
      emailSendState.set(requestKey,{pending:false,until:r.success?Date.now()+60000:0});
      if(form.isConnected&&key()===requestKey){tell(r.success?(r.message||'验证码发送请求已受理')+'。请查看收件箱或垃圾邮件，验证码 10 分钟内有效。':r.error||'发送失败',!r.success);if(r.success)code.focus();}
    }catch(e){emailSendState.set(requestKey,{pending:false,until:Date.now()+60000});if(form.isConnected&&key()===requestKey)tell('未能确认发送结果，请先检查收件箱；一分钟后可以重发。',true);}
    finally{if(form.isConnected)updateSend();}
  });form.append(send);
  email.addEventListener('input',()=>{code.value='';tell('');updateSend();});
  for(const [k,state] of emailSendState)if(!state.pending&&state.until<Date.now()-600000)emailSendState.delete(k);
  function tick(){if(!form.isConnected)return;updateSend();setTimeout(tick,1000);}tick();
  let password,repeat;
  if(kind!=='bind'){
    password=field(form,'新密码',input('',128));password.type='password';password.minLength=8;password.required=true;password.autocomplete='new-password';
    repeat=field(form,'确认新密码',input('',128));repeat.type='password';repeat.required=true;repeat.autocomplete='new-password';
  }
  actions(form,async()=>{
    if(password&&password.value!==repeat.value){tell('两次密码不一致，请重新确认。',true);repeat.focus();return;}
    submitting=true;email.disabled=code.disabled=true;updateSend();tell('正在验证，请稍候…');
    let completed=false;
    try{
    const endpoint=kind==='signup'?'/api/signup':kind==='bind'?'/api/bind-email':'/api/reset-password';
    const r=await api(endpoint,{method:'POST',body:{email:email.value.trim().toLowerCase(),code:code.value.trim(),...(password?{password:password.value}:{})}});
    if(!r.success){tell(r.error||'操作失败',true);return;}
    completed=true;
    closeModal();
    if(kind==='signup'&&!r.pending){SESSION={token:r.session,username:r.username,role:r.role};setCookie('session',r.session,7);await loadData();renderHeaderBtns();render();showToast('邮箱验证成功，注册完成');}
    else if(kind==='signup'){showToast('注册完成，等待管理员审批');}
    else if(kind==='reset'){delCookie('session');SESSION=null;await loadData();renderHeaderBtns();render();showLogin();showToast('密码已重置，请重新登录');}
    else showToast('邮箱已绑定，可用于登录和找回密码');
    }catch(e){if(completed)showToast('操作已完成，但页面刷新失败，请刷新页面后登录。');else tell('连接中断，未能确认操作结果。请先尝试登录或检查绑定状态，再决定是否重试。',true);}
    finally{submitting=false;email.disabled=code.disabled=false;if(form.isConnected)updateSend();}
  },kind==='signup'?'验证并注册':kind==='bind'?'验证并绑定':'验证并重置');
}
function bindMyEmail(){emailFlow('bind');}
changeMyPassword=async function(){try{const r=await api('/api/session');if(!r.success){showLogin();return;}if(!r.email){showToast('请先绑定邮箱，再通过验证码重置密码');bindMyEmail();return;}emailFlow('reset',r.email);}catch(e){showToast('无法读取账号信息，请检查网络后重试');}};
const emailOriginalLogin=showLogin;
showLogin=function(){
  emailOriginalLogin();const form=document.querySelector('#modalContainer .modal')||document.getElementById('loginUser')?.closest('.modal');if(!form)return;
  form.append(button('忘记密码',()=>emailFlow('reset')));
  api('/api/signup-settings').then(s=>{if(s.enabled&&form.isConnected)form.append(button('邮箱注册',()=>emailFlow('signup')));}).catch(()=>{});
};
const emailOriginalAdmin=renderAdmin;
renderAdmin=function(container){
  emailOriginalAdmin(container);
  if(SESSION?.role==='admin'&&adminSection==='system'){
    const panel=el('section',undefined,'admin-section');container.append(panel);renderEmailSettings(panel);
  }
};
async function renderEmailSettings(panel){
  panel.append(el('h3','QQ 邮箱与账号注册'));const status=el('p','正在读取…');panel.append(status);
  try{
    const r=await api('/api/admin/email-settings');if(!r.success)throw Error(r.error||'读取失败');const s=r.settings;
    status.textContent='使用 QQ 邮箱的 SMTP 授权码发送验证码。授权码留空会保留已保存的值，保存后不会回显。';
    const form=el('form',undefined,'traffic-settings');panel.append(form);
    const fields={};
    for(const [key,label] of [['username','QQ 发件邮箱'],['sender','发件人邮箱'],['host','SMTP 服务器'],['port','SMTP 端口'],['password','SMTP 授权码']]){
      const item=field(form,label,input(key==='password'?'':String(s[key]||''),1024));fields[key]=item;
      if(key==='password'){item.type='password';item.autocomplete='new-password';item.placeholder=s.passwordSet?'已保存，留空保持不变':'填写 QQ 邮箱 SMTP 授权码';}
      if(key==='port'){item.type='number';item.min=1;item.max=65535;}
      if(key==='username'||key==='sender')item.type='email';
    }
    fields.username.onchange=()=>{if(!fields.sender.value)fields.sender.value=fields.username.value;};
    const security=el('select');security.add(new Option('SSL/TLS（QQ 默认 465）','ssl'));security.add(new Option('STARTTLS','starttls'));security.value=s.security;field(form,'连接加密',security);
    const enabled=el('input');enabled.type='checkbox';enabled.checked=s.enabled;field(form,'开放邮箱注册',enabled);
    const approval=el('input');approval.type='checkbox';approval.checked=s.approval;field(form,'注册后需要管理员审批（默认关闭）',approval);
    const save=button('保存邮箱设置',()=>{});save.type='submit';save.classList.add('btn-primary');form.append(save);
    form.onsubmit=async e=>{e.preventDefault();save.disabled=true;try{const body={enabled:enabled.checked,approval:approval.checked,security:security.value};for(const [key,input] of Object.entries(fields))body[key]=key==='port'?Number(input.value):input.value;const result=await api('/api/admin/email-settings',{method:'PUT',body});showToast(result.success?'邮箱设置已保存':result.error||'保存失败');if(result.success){fields.password.value='';fields.password.placeholder='已保存，留空保持不变';}}catch(e){showToast('保存失败');}finally{save.disabled=false;}};
    panel.append(el('p','关闭邮箱注册不影响已绑定账号的验证码重置。尚未绑定邮箱的旧账号，请先登录，再在账号菜单绑定。'));
  }catch(e){status.textContent=e.message;}
}

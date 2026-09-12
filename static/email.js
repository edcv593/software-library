// All registration, binding and password recovery use purpose-specific email codes.
function emailFlow(kind,initial=''){
  const title={signup:'邮箱注册',bind:'绑定或更换邮箱',reset:'邮箱重置密码'}[kind];
  const form=modal(title);form.append(el('p',kind==='bind'?'验证码发送到要绑定的新邮箱。':kind==='reset'?'验证码发送到账号已验证的邮箱。重置后所有设备需重新登录。':'验证成功后即可使用账号，下载受站点流量规则限制。'));
  const email=field(form,'邮箱地址',input(initial,254));email.type='email';email.required=true;email.autocomplete='email';
  const code=field(form,'邮件验证码',input('',6));code.required=true;code.pattern='[0-9]{6}';code.inputMode='numeric';code.autocomplete='one-time-code';
  const send=button('发送验证码',async()=>{
    if(!email.reportValidity())return;send.disabled=true;
    try{const endpoint=kind==='signup'?'/api/signup-code':kind==='bind'?'/api/bind-code':'/api/reset-code';const r=await api(endpoint,{method:'POST',body:{email:email.value}});if(!r.success){showToast(r.error||'发送失败');send.disabled=false;return;}showToast(r.message||'验证码已发送');send.textContent='60 秒后可重发';setTimeout(()=>{send.disabled=false;send.textContent='重新发送验证码';},60000);}catch(e){send.disabled=false;showToast('发送失败，请稍后重试');}
  });form.append(send);
  let password,repeat;
  if(kind!=='bind'){
    password=field(form,'新密码',input('',128));password.type='password';password.minLength=8;password.required=true;password.autocomplete='new-password';
    repeat=field(form,'确认新密码',input('',128));repeat.type='password';repeat.required=true;repeat.autocomplete='new-password';
  }
  actions(form,async()=>{
    if(password&&password.value!==repeat.value){showToast('两次密码不一致');return;}
    const endpoint=kind==='signup'?'/api/signup':kind==='bind'?'/api/bind-email':'/api/reset-password';
    const r=await api(endpoint,{method:'POST',body:{email:email.value,code:code.value,...(password?{password:password.value}:{})}});
    if(!r.success){showToast(r.error||'操作失败');return;}
    closeModal();
    if(kind==='signup'&&!r.pending){SESSION={token:r.session,username:r.username,role:r.role};setCookie('session',r.session,7);await loadData();renderHeaderBtns();render();showToast('邮箱验证成功，注册完成');}
    else if(kind==='signup'){showToast('注册完成，等待管理员审批');}
    else if(kind==='reset'){delCookie('session');SESSION=null;await loadData();renderHeaderBtns();render();showLogin();showToast('密码已重置，请重新登录');}
    else showToast('邮箱已绑定，可用于登录和找回密码');
  },kind==='signup'?'验证并注册':kind==='bind'?'验证并绑定':'验证并重置');
}
function bindMyEmail(){emailFlow('bind');}
changeMyPassword=async function(){const r=await api('/api/session');if(!r.email){showToast('请先绑定邮箱，再通过验证码重置密码');bindMyEmail();return;}emailFlow('reset',r.email);};
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

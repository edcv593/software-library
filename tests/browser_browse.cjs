// Run against a local test server with existing accounts. Uses synthetic page data; no writes to the server.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
 const p=await browser.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(process.env.BROWSE_TEST_URL || 'http://127.0.0.1:8926');await p.waitForFunction(()=>ALL_DATA.length);await p.locator('#loginUser').waitFor();await p.evaluate(()=>closeModal());
 await p.evaluate(()=>{CATEGORIES=[{id:'a',name:'工具',parentId:''},{id:'b',name:'系统',parentId:'a'}];ALL_DATA=Array.from({length:53},(_,i)=>({name:'tool-'+i,displayName:'工具 '+i,categoryId:i%2?'a':'b',desc:'test',tags:[],customFields:{},versions:[{path:'tool-'+i+'.exe',filename:'tool-'+i+'.exe',fileType:i%2?'EXE':'ISO',date:'2026-09-'+String(i%28+1).padStart(2,'0'),size:i+1,sizeText:(i+1)+' B',version:'1.0',arch:i%2?'x64':'arm64'}]}));render();});
 assert.equal(await p.locator('.card').count(),24);
 await p.getByRole('button',{name:'下一页',exact:true}).click();assert.match(await p.locator('.browse-summary').innerText(),/25–48/);
 await p.locator('.browse-title').first().click();assert.equal(await p.evaluate(()=>currentSoftware),'tool-24');await p.evaluate(()=>goHome());assert.match(await p.locator('.browse-summary').innerText(),/25–48/);
 await p.getByLabel('文件类型',{exact:true}).selectOption('EXE');assert.match(await p.locator('.browse-summary').innerText(),/共 26 个软件/);assert.match(await p.locator('.browse-summary').innerText(),/1–24/);
 await p.getByLabel('软件排序',{exact:true}).selectOption('size');assert.equal(await p.locator('.browse-title').first().innerText(),'工具 51');
 await p.locator('#searchInput').fill('tool-3 x64');assert.equal(await p.locator('.card').count(),6);
 await p.locator('#searchInput').fill('<img src=x onerror=alert(1)>');assert.equal(await p.locator('.card').count(),0);assert.equal(await p.locator('.browse-summary img').count(),0);
 await p.getByRole('button',{name:'显示全部软件',exact:true}).click();assert.equal(await p.locator('#searchInput').inputValue(),'');assert.equal(await p.locator('.card').count(),24);
 await p.evaluate(()=>selectCategory('a'));assert.match(await p.locator('.browse-summary').innerText(),/共 53 个软件/);
 await p.getByLabel('软件排序',{exact:true}).selectOption('date');assert.equal(await p.locator('.browse-title').first().innerText(),'工具 27');
 await p.setViewportSize({width:390,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 
 await p.setViewportSize({width:1440,height:1000});
 assert.deepEqual(errors,[]);console.log('PASS pagination, identity, return state, type/date/size filters, multi-term version search, safe text, reset, nested category and mobile layout');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});

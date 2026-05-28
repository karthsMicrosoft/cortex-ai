const http = require('http');
const https = require('https');
const ws = require('ws');
const fs = require('fs');

(async () => {
  // Login
  const body = JSON.stringify({email:'karths@microsoft.com',password:'testPWD123*'});
  const tokens = await new Promise((resolve, reject) => {
    const req = https.request('https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
    }, (res) => { let d=''; res.on('data',c=>d+=c); res.on('end',()=>resolve(JSON.parse(d))); });
    req.on('error', reject); req.write(body); req.end();
  });
  
  // Connect CDP
  const tabs = await new Promise((resolve, reject) => {
    http.get('http://127.0.0.1:9222/json', (res) => { let d=''; res.on('data',c=>d+=c); res.on('end',()=>resolve(JSON.parse(d))); }).on('error', reject);
  });
  const tab = tabs.find(t => t.url.includes('gentle-river')) || tabs[0];
  const socket = new ws(tab.webSocketDebuggerUrl);
  await new Promise(r => socket.on('open', r));
  
  let id = 0;
  const send = (method, params={}) => new Promise((resolve, reject) => {
    const myId = ++id;
    const timeout = setTimeout(() => reject(new Error('cdp timeout')), 20000);
    socket.send(JSON.stringify({ id: myId, method, params }));
    const handler = (msg) => {
      try { const d = JSON.parse(msg.toString()); if (d.id === myId) { clearTimeout(timeout); socket.off('message', handler); resolve(d.result); } } catch {}
    };
    socket.on('message', handler);
  });
  
  // Set viewport
  await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
  
  // Navigate, set token, navigate to brain
  await send('Page.navigate', { url: 'https://gentle-river-06c1e4e10.7.azurestaticapps.net/' });
  await new Promise(r => setTimeout(r, 2000));
  await send('Runtime.evaluate', { expression: "localStorage.setItem('access_token', '" + tokens.access_token + "')" });
  await send('Runtime.evaluate', { expression: "localStorage.setItem('refresh_token', '" + tokens.refresh_token + "')" });
  
  await send('Page.navigate', { url: 'https://gentle-river-06c1e4e10.7.azurestaticapps.net/brain' });
  await new Promise(r => setTimeout(r, 12000));
  
  const result = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync('C:/Users/karths/.copilot/session-state/768d769e-745b-45b0-bcb2-dd1c0eb927a4/files/brain-3d-after-fix.png', Buffer.from(result.data, 'base64'));
  console.log('Done');
  
  await send('Emulation.clearDeviceMetricsOverride');
  socket.close();
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
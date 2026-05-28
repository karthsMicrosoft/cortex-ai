const http = require('http');
const https = require('https');
const ws = require('ws');
const fs = require('fs');

function apiLogin() {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({email:'karths@microsoft.com',password:'testPWD123*'});
    const req = https.request('https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
    }, (res) => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => resolve(JSON.parse(d)));
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

(async () => {
  const tokens = await apiLogin();
  console.log('Got access_token:', !!tokens.access_token);
  
  const tabsJson = await new Promise((resolve, reject) => {
    http.get('http://127.0.0.1:9222/json', (res) => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => resolve(JSON.parse(d)));
    }).on('error', reject);
  });
  
  const tab = tabsJson.find(t => t.url.includes('gentle-river')) || tabsJson[0];
  const socket = new ws(tab.webSocketDebuggerUrl);
  await new Promise(r => socket.on('open', r));
  
  let id = 0;
  const send = (method, params = {}) => new Promise(r => {
    const myId = ++id;
    socket.send(JSON.stringify({ id: myId, method, params }));
    const handler = (msg) => {
      const data = JSON.parse(msg.toString());
      if (data.id === myId) { socket.off('message', handler); r(data.result); }
    };
    socket.on('message', handler);
  });
  
  // Navigate to blank first to set localStorage on correct origin
  await send('Page.navigate', { url: 'https://gentle-river-06c1e4e10.7.azurestaticapps.net/' });
  await new Promise(r => setTimeout(r, 2000));
  
  // Set tokens
  await send('Runtime.evaluate', { expression: "localStorage.setItem('access_token', '" + tokens.access_token + "')" });
  await send('Runtime.evaluate', { expression: "localStorage.setItem('refresh_token', '" + tokens.refresh_token + "')" });
  console.log('Tokens stored');
  
  // Navigate to brain
  await send('Page.navigate', { url: 'https://gentle-river-06c1e4e10.7.azurestaticapps.net/brain' });
  console.log('Navigating to /brain...');
  await new Promise(r => setTimeout(r, 12000));
  
  const result = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync('C:/Users/karths/.copilot/session-state/768d769e-745b-45b0-bcb2-dd1c0eb927a4/files/brain-3d-after-fix.png', Buffer.from(result.data, 'base64'));
  console.log('Screenshot saved');
  
  socket.close();
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });

const http = require('http');
const ws = require('ws');
const fs = require('fs');

(async () => {
  const tabsJson = await new Promise((resolve, reject) => {
    http.get('http://127.0.0.1:9222/json', (res) => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => resolve(JSON.parse(d)));
    }).on('error', reject);
  });
  
  const tab = tabsJson.find(t => t.url.includes('brain')) || tabsJson[0];
  console.log('Tab:', tab.url);
  const socket = new ws(tab.webSocketDebuggerUrl);
  await new Promise(r => socket.on('open', r));
  
  let msgId = 0;
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const myId = ++msgId;
    const timeout = setTimeout(() => reject(new Error('timeout')), 15000);
    socket.send(JSON.stringify({ id: myId, method, params }));
    const handler = (msg) => {
      try {
        const data = JSON.parse(msg.toString());
        if (data.id === myId) {
          clearTimeout(timeout);
          socket.off('message', handler);
          resolve(data.result);
        }
      } catch {}
    };
    socket.on('message', handler);
  });
  
  // Check page content
  const html = await send('Runtime.evaluate', { expression: "document.body.innerText.substring(0, 500)" });
  console.log('Page text:', html.result.value);
  
  const url = await send('Runtime.evaluate', { expression: "window.location.href" });
  console.log('URL:', url.result.value);
  
  const auth = await send('Runtime.evaluate', { expression: "localStorage.getItem('access_token') ? 'yes' : 'no'" });
  console.log('Auth:', auth.result.value);
  
  // Get viewport info
  const dims = await send('Runtime.evaluate', { expression: "JSON.stringify({w:window.innerWidth,h:window.innerHeight,dpr:window.devicePixelRatio})" });
  console.log('Viewport:', dims.result.value);
  
  // Set a proper viewport
  await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
  await new Promise(r => setTimeout(r, 2000));
  
  // Full page screenshot
  const result = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  fs.writeFileSync('C:/Users/karths/.copilot/session-state/768d769e-745b-45b0-bcb2-dd1c0eb927a4/files/brain-3d-after-fix.png', Buffer.from(result.data, 'base64'));
  console.log('Screenshot saved');
  
  // Clear override
  await send('Emulation.clearDeviceMetricsOverride');
  
  socket.close();
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });

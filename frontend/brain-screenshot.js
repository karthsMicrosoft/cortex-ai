const http = require('http');
const ws = require('ws');
const fs = require('fs');

function connect() {
  return new Promise((resolve, reject) => {
    http.get('http://127.0.0.1:9222/json', (res) => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => {
        const tabs = JSON.parse(d);
        const socket = new ws(tabs[0].webSocketDebuggerUrl);
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
        socket.on('open', () => resolve({ socket, send }));
        socket.on('error', reject);
      });
    }).on('error', reject);
  });
}

(async () => {
  const { socket, send } = await connect();
  
  await send('Page.navigate', { url: 'https://gentle-river-06c1e4e10.7.azurestaticapps.net/' });
  await new Promise(r => setTimeout(r, 3000));
  
  const token = await send('Runtime.evaluate', { expression: "localStorage.getItem('access_token') ? 'yes' : 'no'" });
  console.log('Auth:', token.result.value);
  
  if (token.result.value === 'no') {
    await send('Runtime.evaluate', { expression: "document.querySelector('input[type=email]').value = 'karths@microsoft.com'" });
    await send('Runtime.evaluate', { expression: "document.querySelector('input[type=email]').dispatchEvent(new Event('input', {bubbles:true}))" });
    await send('Runtime.evaluate', { expression: "document.querySelector('input[type=password]').value = 'testPWD123*'" });
    await send('Runtime.evaluate', { expression: "document.querySelector('input[type=password]').dispatchEvent(new Event('input', {bubbles:true}))" });
    await send('Runtime.evaluate', { expression: "document.querySelector('button[type=submit]').click()" });
    await new Promise(r => setTimeout(r, 3000));
    console.log('Logged in');
  }
  
  await send('Page.navigate', { url: 'https://gentle-river-06c1e4e10.7.azurestaticapps.net/brain' });
  await new Promise(r => setTimeout(r, 10000));
  
  const result = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync('C:/Users/karths/.copilot/session-state/768d769e-745b-45b0-bcb2-dd1c0eb927a4/files/brain-3d-after-fix.png', Buffer.from(result.data, 'base64'));
  console.log('Screenshot saved');
  
  socket.close();
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });

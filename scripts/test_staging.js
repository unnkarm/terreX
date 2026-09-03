const http = require('http');

function post(path, body = {}) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const req = http.request({
      hostname: 'localhost',
      port: 8000,
      path: path,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
    }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(data) });
        } catch (e) {
          resolve({ status: res.statusCode, raw: data });
        }
      });
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

function get(path) {
  return new Promise((resolve, reject) => {
    http.get(`http://localhost:8000${path}`, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(data) });
        } catch (e) {
          resolve({ status: res.statusCode, raw: data });
        }
      });
    }).on('error', reject);
  });
}

async function run() {
  console.log('Testing process-incoming...');
  const res = await post('/api/ingest/process-incoming');
  console.log('Process status:', res.status);
  console.log('Metrics:', JSON.stringify(res.data?.metrics, null, 2));
  console.log('Processed scenes:', res.data?.processed?.map(p => ({ filename: p.filename, status: p.status, tiles: p.created_tiles })));
  console.log('Failed:', res.data?.failed);

  console.log('\nChecking scenes in database...');
  const scenes = await get('/api/ingest/scenes');
  console.log('Scenes count:', scenes.data?.length);
  console.log('Scenes summary:', scenes.data?.map(s => ({ filename: s.source_filename, sensor: s.sensor, date: s.acquisition_date, tiles: s.tile_count })));
}

run().catch(console.error);

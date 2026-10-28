// Diagnostik: reproduksi bug "tombol Simpan/Batal tidak berfungsi"
const puppeteer = require('puppeteer-core');

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/chromium',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });

  await page.goto('http://127.0.0.1:8080/', { waitUntil: 'networkidle2', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 800));

  // 1. Status modal saat halaman baru dimuat (harusnya semua tersembunyi)
  const modals = await page.evaluate(() => {
    const out = {};
    for (const id of ['settingsModal', 'arenaModal', 'viewerModal']) {
      const el = document.getElementById(id);
      const cs = getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      out[id] = {
        attributHidden: el.hidden,
        displayTerhitung: cs.display,
        terlihatDiLayar: cs.display !== 'none' && rect.width > 0,
      };
    }
    return out;
  });
  console.log('=== STATUS MODAL SAAT LOAD ===');
  for (const [k, v] of Object.entries(modals)) {
    console.log(`${k}: hidden=${v.attributHidden} | display=${v.displayTerhitung} | terlihat=${v.terlihatDiLayar} ${v.terlihatDiLayar && v.attributHidden ? '  <-- BUG! [hidden] dikalahkan CSS' : ''}`);
  }

  // 2. Klik Batal pada modal pengaturan (jika terlihat)
  try {
    await page.evaluate(() => { document.getElementById('settingsModal').hidden = false; });
    await new Promise((r) => setTimeout(r, 200));
    const before = await page.evaluate(() => getComputedStyle(document.getElementById('settingsModal')).display);
    await page.click('#settingsModal [data-close]');
    await new Promise((r) => setTimeout(r, 300));
    const after = await page.evaluate(() => {
      const el = document.getElementById('settingsModal');
      return { hidden: el.hidden, display: getComputedStyle(el).display };
    });
    console.log('\n=== TES TOMBOL BATAL ===');
    console.log('sebelum klik : display=' + before);
    console.log('setelah klik : hidden=' + after.hidden + ' display=' + after.display + (after.display !== 'none' ? '  <-- BUG! modal tidak menutup' : '  OK'));
  } catch (e) {
    console.log('error tes batal:', e.message);
  }

  console.log('\n=== ERROR JS ===');
  console.log(errors.length ? errors.join('\n') : '(tidak ada)');
  await browser.close();
})().catch((e) => { console.error('FATAL:', e.message); process.exit(1); });

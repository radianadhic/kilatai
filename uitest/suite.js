// Suite pengujian fungsional lengkap Kilat AI (headless Chromium)
const puppeteer = require('puppeteer-core');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0, fail = 0;
function ok(kondisi, label) {
  if (kondisi) { pass++; console.log('  LULUS  ' + label); }
  else { fail++; console.log('  GAGAL  ' + label); }
}

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
  await sleep(1000);

  const disp = (sel) => page.evaluate((s) => getComputedStyle(document.querySelector(s)).display, sel);

  console.log('== 1. Modal tersembunyi saat load ==');
  for (const id of ['settingsModal', 'arenaModal', 'viewerModal']) {
    ok(await disp('#' + id) === 'none', `${id} tersembunyi`);
  }

  console.log('== 2. Tombol Batal modal Pengaturan ==');
  await page.click('#settingsBtn'); await sleep(250);
  ok(await disp('#settingsModal') === 'flex', 'modal terbuka setelah klik ⚙️');
  await page.click('#settingsModal [data-close]'); await sleep(250);
  ok(await disp('#settingsModal') === 'none', 'modal tertutup setelah klik Batal');

  console.log('== 3. Simpan Pengaturan ==');
  await page.click('#settingsBtn'); await sleep(250);
  await page.click('#saveSettingsBtn'); await sleep(250);
  ok(await disp('#settingsModal') === 'none', 'modal tertutup setelah klik Simpan');

  console.log('== 4. Mode Arena: default tercentang + Simpan ==');
  await page.click('#arenaBtn'); await sleep(250);
  ok(await disp('#arenaModal') === 'flex', 'modal Arena terbuka');
  const cek = await page.$$eval('#arModels input[data-ar]', (els) => els.map((e) => ({ n: e.getAttribute('data-ar'), c: e.checked })));
  ok(cek.length === 3, 'ada 3 model demo di daftar');
  ok(cek.filter((x) => x.c).length === 3, 'ketiganya tercentang default (rekomendasi)');
  const juri = await page.$eval('#arJudge', (e) => e.value);
  ok(!!juri, 'juri terisi default: ' + juri);
  await page.click('#arEnable'); // aktifkan Mode Arena
  await page.click('#saveArenaBtn'); await sleep(300);
  ok(await disp('#arenaModal') === 'none', 'modal Arena tertutup setelah Simpan');
  const chip = await page.$eval('#arenaBtn', (e) => e.textContent.trim());
  ok(/Arena: ON \(3\)/.test(chip), 'chip header: "' + chip + '"');

  console.log('== 5. Obrolan Mode Arena end-to-end (3 model + juri) ==');
  await page.type('#input', 'apa itu ollama?');
  await page.keyboard.press('Enter');
  await sleep(9000); // tunggu 3 model bergantian + juri (server demo)
  const nKartu = (await page.$$('.arena-card')).length;
  ok(nKartu === 3, '3 kartu jawaban model (' + nKartu + ')');
  const vonis = await page.evaluate(() => {
    const v = document.querySelector('.verdict');
    return v ? v.textContent.trim().slice(0, 90) : null;
  });
  ok(!!vonis, 'vonis juri tampil: "' + vonis + '"');
  const adaMenang = await page.evaluate(() => !!document.querySelector('.arena-card.win'));
  ok(adaMenang, 'kartu jawaban terbaik ditandai');

  console.log('== 6. Matikan Mode Arena via Batal ==');
  await page.click('#arenaBtn'); await sleep(250);
  await page.click('#arEnable'); // matikan centang
  await page.click('#saveArenaBtn'); await sleep(300);
  const chip2 = await page.$eval('#arenaBtn', (e) => e.textContent.trim());
  ok(/Arena: OFF/.test(chip2), 'chip kembali: "' + chip2 + '"');

  console.log('== 7. Chat biasa + tools treasury ==');
  await page.type('#input', 'berapa saldo kas kita?');
  await page.keyboard.press('Enter');
  await sleep(6000);
  const jawab = await page.evaluate(() => {
    const m = [...document.querySelectorAll('.msg.ai .md')].pop();
    return m ? m.textContent.slice(0, 80) : null;
  });
  ok(!!jawab && /treasury|demo/i.test(jawab), 'jawaban AI diterima: "' + (jawab || '') + '"...');

  console.log('\n== ERROR JS SELAMA SESI ==');
  console.log(errors.length ? errors.join('\n') : '(tidak ada)');
  ok(errors.length === 0, 'tidak ada error JavaScript');

  console.log(`\nTOTAL: ${pass} lulus, ${fail} gagal`);
  await browser.close();
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error('FATAL:', e.message); process.exit(2); });

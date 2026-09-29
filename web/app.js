const $ = (id) => document.getElementById(id);
let folders = [];
let jobs = [];
let root = null;
let platform = 'tiktok';
const selected = new Set();
const cookiePaths = { tiktok: '', youtube: '', instagram: '' };
const cookieTexts = { tiktok: '', youtube: '', instagram: '' };
const cookieBrowsers = { tiktok: '', youtube: '', instagram: '' };
const cookieSaveTimers = {};

async function api(path, options = {}) {
  const response = await fetch('/api/' + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Something went wrong.');
  return data;
}

function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').classList.toggle('error', error);
}

function showCookieSettings() {
  $('cookiefile').value = cookiePaths[platform];
  $('cookiesText').value = cookieTexts[platform];
  $('cookieBrowser').value = cookieBrowsers[platform];
  $('cookieSaveStatus').textContent = 'Saved automatically on this computer';
}

async function loadCookieSettings() {
  try {
    const { settings } = await api('cookies');
    for (const name of Object.keys(cookiePaths)) {
      cookiePaths[name] = settings[name]?.cookiefile || '';
      cookieTexts[name] = settings[name]?.cookies_text || '';
      cookieBrowsers[name] = settings[name]?.browser || '';
    }
    showCookieSettings();
  } catch (error) { $('cookieSaveStatus').textContent = 'Could not load saved cookies'; notice(error.message, true); }
}

async function saveCookieSettings(name) {
  clearTimeout(cookieSaveTimers[name]);
  if (name === platform) $('cookieSaveStatus').textContent = 'Saving…';
  await api('cookies', { method: 'POST', body: JSON.stringify({ platform: name, cookiefile: cookiePaths[name], cookies_text: cookieTexts[name], browser: cookieBrowsers[name] }) });
  if (name === platform) $('cookieSaveStatus').textContent = 'Saved automatically on this computer';
}

function saveCookieSoon(name) {
  clearTimeout(cookieSaveTimers[name]);
  $('cookieSaveStatus').textContent = 'Saving…';
  cookieSaveTimers[name] = setTimeout(() => saveCookieSettings(name).catch(error => { if (name === platform) $('cookieSaveStatus').textContent = 'Save failed'; notice(error.message, true); }), 500);
}

function renderFolders() {
  const list = $('folderList');
  list.replaceChildren();
  if (!root) {
    list.innerHTML = '<div class="empty">Choose a root folder to see its creator folders.</div>';
  } else if (!folders.length) {
    list.innerHTML = '<div class="empty">No subfolders found. Add creator username folders inside the root folder, then rescan.</div>';
  } else {
    for (const folder of folders) {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'folder-row' + (selected.has(folder.name) ? ' selected' : '');
      row.setAttribute('aria-pressed', selected.has(folder.name));
      row.disabled = !folder.valid;
      if (!folder.valid) row.title = 'Folder name must be a creator username.';
      const checkbox = document.createElement('span');
      checkbox.className = 'checkbox';
      checkbox.textContent = selected.has(folder.name) ? '✓' : '';
      const glyph = document.createElement('span');
      glyph.className = 'folder-glyph'; glyph.textContent = '▤';
      const name = document.createElement('span');
      name.className = 'folder-name'; name.textContent = folder.name;
      const count = document.createElement('span');
      count.className = 'folder-count' + (folder.count === 0 ? ' zero' : '');
      count.textContent = folder.valid ? `${folder.count} video${folder.count === 1 ? '' : 's'}` : 'Invalid username';
      row.append(checkbox, glyph, name, count);
      row.onclick = () => { selected.has(folder.name) ? selected.delete(folder.name) : selected.add(folder.name); renderFolders(); };
      list.append(row);
    }
  }
  $('selectionCount').textContent = `${selected.size} selected · Sorted by fewest videos`;
  const selectable = folders.filter(folder => folder.valid);
  $('selectAll').textContent = selected.size === selectable.length && selectable.length ? 'Clear selection' : 'Select all';
  const threshold = Number($('limit').value);
  $('selectUnder').textContent = `Select under ${Number.isInteger(threshold) && threshold >= 0 ? threshold : 10} videos`;
  $('statFolders').textContent = folders.length;
  $('statVideos').textContent = folders.reduce((total, folder) => total + folder.count, 0);
  $('rootPath').textContent = root || 'No folder selected';
  $('rootPath').title = root || '';
}

async function scan() {
  try {
    const result = await api('folders');
    root = result.root;
    folders = result.folders;
    for (const name of selected) if (!folders.some(folder => folder.name === name && folder.valid)) selected.delete(name);
    renderFolders();
  } catch (error) { notice(error.message, true); }
}

async function chooseRoot() {
  try {
    const result = await api('choose-folder', { method: 'POST' });
    if (result.root) { if (result.root !== root) selected.clear(); await scan(); notice('Root folder ready. Select creator folders to download.'); }
  } catch (error) { notice(error.message, true); }
}

function renderJobs() {
  const list = $('queueList');
  list.replaceChildren();
  $('queueBadge').textContent = jobs.length;
  $('statDone').textContent = jobs.filter(job => job.status === 'Done').length;
  $('statActive').textContent = jobs.filter(job => ['Starting', 'Downloading', 'Processing', 'Resolving TikTok profile', 'Stopping'].includes(job.status)).length;
  $('stop').disabled = !jobs.some(job => ['Queued', 'Starting', 'Downloading', 'Processing', 'Resolving TikTok profile'].includes(job.status));
  if (!jobs.length) {
    list.innerHTML = '<div class="queue-empty"><span>↓</span><strong>Your queue is looking a little quiet</strong><p>Select creator folders above to get things moving.</p></div>';
    return;
  }
  for (const job of [...jobs].reverse()) {
    const row = document.createElement('div'); row.className = 'job-row';
    const icon = document.createElement('span'); icon.className = 'job-icon'; icon.textContent = '↓';
    const main = document.createElement('div'); main.className = 'job-main';
    const title = document.createElement('strong'); title.textContent = job.title || job.folder;
    const url = document.createElement('small'); url.textContent = job.detail || `${job.folder} · ${job.url}`; url.title = job.detail || job.url;
    main.append(title, url);
    const progress = document.createElement('div'); progress.className = 'progress-wrap';
    const bar = document.createElement('span'); bar.className = 'progress-bar';
    const fill = document.createElement('i'); fill.style.width = `${Math.max(0, Math.min(job.progress, 100))}%`; bar.append(fill);
    const pct = document.createElement('span'); pct.textContent = `${job.progress}%`; progress.append(bar, pct);
    const status = document.createElement('span'); status.className = 'job-status ' + job.status; status.textContent = job.status;
    row.append(icon, main, progress, status); list.append(row);
  }
}

async function refreshJobs() {
  try { const result = await api('status'); jobs = result.jobs; renderJobs(); }
  catch (error) { notice('Connection to the local downloader was lost.', true); }
}

async function addQueue() {
  const limit = Number($('limit').value);
  const concurrency = Number($('concurrency').value);
  if (!root) return notice('Choose a root folder first.', true);
  if (!selected.size) return notice('Select at least one creator folder first.', true);
  if (!Number.isInteger(limit) || limit < 0 || !Number.isInteger(concurrency) || concurrency < 1 || concurrency > 8) return notice('Use a video limit of 0 or more and 1–8 concurrent downloads.', true);
  try {
    await saveCookieSettings(platform);
    const result = await api('queue', { method: 'POST', body: JSON.stringify({ platform, folders: [...selected], limit, concurrency, cookiefile: cookiePaths[platform].trim(), cookies_text: cookieTexts[platform], browser: cookieBrowsers[platform] }) });
    notice(`${result.queued} creator folder${result.queued === 1 ? '' : 's'} added to the queue.`);
    await scan();
    await refreshJobs();
    $('queue').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) { notice(error.message, true); }
}

$('chooseRoot').onclick = chooseRoot;
$('chooseRootHero').onclick = chooseRoot;
$('rescan').onclick = scan;
$('selectAll').onclick = () => { const selectable = folders.filter(folder => folder.valid); if (selected.size === selectable.length) selected.clear(); else selectable.forEach(folder => selected.add(folder.name)); renderFolders(); };
$('selectUnder').onclick = () => {
  const threshold = Number($('limit').value);
  if (!Number.isInteger(threshold) || threshold <= 0) return notice('Enter a video number greater than 0 first.', true);
  selected.clear();
  folders.filter(folder => folder.valid && folder.count < threshold).forEach(folder => selected.add(folder.name));
  renderFolders();
  notice(`${selected.size} folder${selected.size === 1 ? '' : 's'} with fewer than ${threshold} videos selected.`);
};
$('limit').addEventListener('input', renderFolders);
$('addQueue').onclick = addQueue;
$('browseCookies').onclick = async () => {
  try { const result = await api('choose-cookies', { method: 'POST' }); if (result.path) { $('cookiefile').value = result.path; cookiePaths[platform] = result.path; saveCookieSoon(platform); } }
  catch (error) { notice(error.message, true); }
};
$('cookiefile').addEventListener('input', () => { cookiePaths[platform] = $('cookiefile').value; saveCookieSoon(platform); });
$('cookiesText').addEventListener('input', () => { cookieTexts[platform] = $('cookiesText').value; saveCookieSoon(platform); });
$('cookieBrowser').addEventListener('change', () => { cookieBrowsers[platform] = $('cookieBrowser').value; saveCookieSoon(platform); });
$('clearCookies').onclick = async () => {
  cookiePaths[platform] = ''; cookieTexts[platform] = ''; cookieBrowsers[platform] = '';
  showCookieSettings();
  try { await saveCookieSettings(platform); notice(`${platform} cookie settings cleared.`); }
  catch (error) { $('cookieSaveStatus').textContent = 'Clear failed'; notice(error.message, true); }
};
document.querySelectorAll('[data-platform]').forEach(button => button.onclick = () => {
  cookiePaths[platform] = $('cookiefile').value;
  cookieTexts[platform] = $('cookiesText').value;
  cookieBrowsers[platform] = $('cookieBrowser').value;
  platform = button.dataset.platform;
  document.querySelectorAll('[data-platform]').forEach(item => { const active = item === button; item.classList.toggle('selected', active); item.setAttribute('aria-pressed', active); });
  showCookieSettings();
});
$('stop').onclick = async () => { try { await api('stop', { method: 'POST' }); await refreshJobs(); notice('Stopping active downloads and clearing the queue.'); } catch (error) { notice(error.message, true); } };
scan(); refreshJobs(); loadCookieSettings(); setInterval(refreshJobs, 1000); setInterval(scan, 15000);

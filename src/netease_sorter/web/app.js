// 纯手写，无依赖。数据来自 /api/data，生成脚本走 /api/script。

const state = {
  songs: [],
  meta: {},
  account: null,
  languages: [],
  langs: new Set(),
  genres: new Set(),
  q: "",
  review: false,
  page: 0,
  pageSize: 50,
  selected: new Set(),
};

const $ = (sel) => document.querySelector(sel);
const CONF_LABEL = { high: "高", mid: "中", low: "低", manual: "人工" };

function countBy(list, key) {
  const map = new Map();
  for (const item of list) {
    const value = key(item);
    for (const v of Array.isArray(value) ? value : [value]) {
      map.set(v, (map.get(v) || 0) + 1);
    }
  }
  return map;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// ---------------------------------------------------------------- 数据
async function boot() {
  try {
    const res = await fetch("/api/data");
    const data = await res.json();
    if (data.error) return showEmpty(data.error);
    state.songs = data.songs || [];
    state.meta = data.playlist || {};
    state.account = data.account || null;
    state.languages = data.languages || [];
    renderSub();
    renderAccount();
    renderChips();
    render();
  } catch (err) {
    showEmpty("加载失败：" + err.message);
  }
}

function renderSub() {
  const { name, count, updated } = state.meta;
  const bits = [];
  if (name) bits.push(`《${name}》`);
  bits.push(`${count || state.songs.length} 首`);
  if (updated) bits.push(`更新于 ${updated}`);
  $("#sub").textContent = bits.join(" · ");
}

function renderAccount() {
  const node = $("#account");
  if (state.account && state.account.uid) {
    node.textContent = `已登录：${state.account.nickname || state.account.uid} · 筛选后可直接写入账号`;
    node.className = "account online";
  } else {
    node.textContent = "未登录 · 只能生成 Console 脚本；要直接写歌单，先在命令行运行 netease-sorter login --from-edge";
    node.className = "account offline";
  }
}

function showEmpty(message) {
  $("#sub").textContent = "没有可展示的数据";
  const tbody = $("#rows");
  tbody.innerHTML = "";
  const tr = el("tr");
  const td = el("td", "empty");
  td.colSpan = 7;
  td.append(el("div", "", message));
  td.append(el("div", "dim", "先在命令行运行：netease-sorter fetch --playlist <id> && netease-sorter classify"));
  tr.append(td);
  tbody.append(tr);
}

// ---------------------------------------------------------------- 筛选
function matches(song) {
  if (state.langs.size && !state.langs.has(song.lang)) return false;
  if (state.genres.size && !song.genres.some((g) => state.genres.has(g))) return false;
  if (state.review && !["low", "mid"].includes(song.confidence)) return false;
  if (state.q) {
    const hay = `${song.name} ${song.artists} ${song.album}`.toLowerCase();
    if (!hay.includes(state.q)) return false;
  }
  return true;
}

function filtered() {
  return state.songs.filter(matches);
}

// ---------------------------------------------------------------- 渲染
function renderChips() {
  const langCount = countBy(state.songs, (s) => s.lang);
  const langBox = $("#langChips");
  langBox.innerHTML = "";

  const allChip = el("button", "chip" + (state.langs.size === 0 ? " on" : ""));
  allChip.type = "button";
  allChip.title = "清空语种筛选";
  allChip.append(document.createTextNode("全部"));
  allChip.append(el("b", "", String(state.songs.length)));
  allChip.addEventListener("click", () => {
    state.langs.clear();
    state.page = 0;
    renderChips();
    render();
  });
  langBox.append(allChip);

  for (const [lang, n] of langCount) {
    const chip = el("button", "chip" + (state.langs.has(lang) ? " on" : ""));
    chip.type = "button";
    chip.append(document.createTextNode(lang));
    chip.append(el("b", "", String(n)));
    chip.addEventListener("click", () => {
      if (state.langs.has(lang)) state.langs.delete(lang);
      else state.langs.add(lang);
      state.page = 0;
      renderChips();
      render();
    });
    langBox.append(chip);
  }

  const genreCount = countBy(state.songs, (s) => s.genres);
  const genreBox = $("#genreChips");
  genreBox.innerHTML = "";
  const sorted = [...genreCount.entries()].sort((a, b) => b[1] - a[1]);
  for (const [genre, n] of sorted) {
    const chip = el("button", "chip" + (state.genres.has(genre) ? " on" : ""));
    chip.type = "button";
    chip.append(document.createTextNode(genre));
    chip.append(el("b", "", String(n)));
    chip.addEventListener("click", () => {
      if (state.genres.has(genre)) state.genres.delete(genre);
      else state.genres.add(genre);
      state.page = 0;
      renderChips();
      render();
    });
    genreBox.append(chip);
  }
}

function renderRows(rows) {
  const tbody = $("#rows");
  tbody.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const song of rows) {
    const tr = el("tr", state.selected.has(song.id) ? "picked" : "");
    tr.dataset.id = String(song.id);

    const pick = el("td", "pick");
    const box = el("input");
    box.type = "checkbox";
    box.checked = state.selected.has(song.id);
    box.addEventListener("change", () => toggle(song.id));
    pick.append(box);

    const name = el("td", "name", song.name || "—");
    const artists = el("td", "dim", song.artists || "—");
    const album = el("td", "dim album", song.album || "—");

    const lang = el("td");
    lang.append(el("span", "badge lang", song.lang));

    const genreTd = el("td");
    if (song.genres.length) {
      for (const g of song.genres) genreTd.append(el("span", "badge", g));
    } else {
      genreTd.append(el("span", "dim", "—"));
    }

    const conf = el("td");
    conf.append(el("span", `badge conf-${song.confidence}`, CONF_LABEL[song.confidence] || song.confidence));

    tr.append(pick, name, artists, album, lang, genreTd, conf);
    tr.addEventListener("click", (event) => {
      if (event.target.tagName === "INPUT") return;
      toggle(song.id);
    });
    frag.append(tr);
  }
  tbody.append(frag);
}

function toggle(id) {
  if (state.selected.has(id)) state.selected.delete(id);
  else state.selected.add(id);
  const row = document.querySelector(`tr[data-id="${id}"]`);
  if (row) {
    row.classList.toggle("picked", state.selected.has(id));
    const box = row.querySelector('input[type="checkbox"]');
    if (box) box.checked = state.selected.has(id);
  }
  updateCount();
}

function updateCount() {
  const shown = filtered();
  const selectedText = state.selected.size ? `　已选 <b>${state.selected.size}</b> 首` : "";
  $("#count").innerHTML = `筛选出 <b>${shown.length}</b> 首 / 共 ${state.songs.length} 首${selectedText}`;
}

function render() {
  const rows = filtered();
  const pages = Math.max(1, Math.ceil(rows.length / state.pageSize));
  state.page = Math.min(state.page, pages - 1);
  const start = state.page * state.pageSize;
  renderRows(rows.slice(start, start + state.pageSize));

  $("#pageInfo").textContent = `第 ${state.page + 1} / ${pages} 页`;
  $("#prev").disabled = state.page === 0;
  $("#next").disabled = state.page >= pages - 1;
  updateCount();

  $("#stats").innerHTML = `
    <div><b>${state.songs.length}</b><span>总曲目</span></div>
    <div><b>${rows.length}</b><span>当前筛选</span></div>
    <div><b>${state.selected.size}</b><span>已选择</span></div>`;
}

// ---------------------------------------------------------------- 动作
function selectAllFiltered() {
  for (const song of filtered()) state.selected.add(song.id);
  render();
}

function clearSelection() {
  state.selected.clear();
  render();
}

function exportCsv() {
  const rows = filtered();
  if (!rows.length) return alert("当前筛选结果为空");
  const header = ["id", "歌名", "歌手", "专辑", "语种", "曲风", "置信度"];
  const esc = (v) => `"${String(v).replace(/"/g, '""')}"`;
  const lines = [header.join(",")];
  for (const s of rows) {
    lines.push([s.id, s.name, s.artists, s.album, s.lang, s.genres.join(" / "), s.confidence].map(esc).join(","));
  }
  download("\ufeff" + lines.join("\r\n"), "筛选结果.csv", "text/csv;charset=utf-8");
}

function defaultName() {
  const bits = [];
  if (state.langs.size) bits.push([...state.langs].join("+"));
  if (state.genres.size) bits.push([...state.genres].join("、"));
  return "我的歌单 · " + (bits.join(" · ") || "自定义");
}

async function makeScript() {
  const ids = state.selected.size ? [...state.selected] : filtered().map((s) => s.id);
  if (!ids.length) return alert("没有可写入的歌曲");

  $("#playlistName").value = defaultName();
  $("#modalHint").textContent = state.account
    ? `将写入 ${ids.length} 首，点「直接写入账号」即可；也可以复制脚本到浏览器执行。`
    : `将写入 ${ids.length} 首。没有登录态，只能复制脚本到 music.163.com 的 Console 执行。`;
  $("#scriptOut").value = "生成中…";
  $("#writeStatus").hidden = true;
  $("#modal").showModal();
  await regenerate(ids);
}

let currentIds = [];

function setWriteStatus(text, kind = "", url = "") {
  const box = $("#writeStatus");
  box.hidden = false;
  box.className = "write-status" + (kind ? " " + kind : "");
  box.textContent = text;
  if (url) {
    box.append(" ");
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "打开歌单";
    box.append(link);
  }
}

async function directWrite() {
  if (!currentIds.length) return;
  const name = $("#playlistName").value.trim();
  if (!name) return alert("先填歌单名");
  if (!state.account) {
    return setWriteStatus("没有登录态：先在命令行运行 netease-sorter login --from-edge，然后刷新本页", "err");
  }
  const btn = $("#directWrite");
  btn.disabled = true;
  setWriteStatus("准备写入…");
  try {
    const res = await fetch("/api/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ids: currentIds,
        name,
        append: $("#appendMode").checked,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "创建失败");
    await pollCreate(data.job);
  } catch (err) {
    setWriteStatus("失败：" + err.message, "err");
  } finally {
    btn.disabled = false;
  }
}

function pollCreate(id) {
  return new Promise((resolve) => {
    const timer = setInterval(async () => {
      let job;
      try {
        job = await (await fetch("/api/job?id=" + id)).json();
      } catch {
        return;
      }
      if (job.status === "running") {
        const percent = job.total ? Math.round((job.progress / job.total) * 100) : 0;
        setWriteStatus(`${job.message}（${percent}%）`);
      } else if (job.status === "done") {
        clearInterval(timer);
        const result = job.result || {};
        const extra = result.written ? `，本次写入 ${result.written} 首` : "";
        setWriteStatus(`${job.message}${extra}`, "ok", result.url);
        resolve();
      } else {
        clearInterval(timer);
        setWriteStatus("失败：" + job.message, "err");
        resolve();
      }
    }, 800);
  });
}

async function regenerate(ids) {
  currentIds = ids || currentIds;
  const name = $("#playlistName").value.trim() || "我的歌单";
  try {
    const res = await fetch("/api/script", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: currentIds, name }),
    });
    const data = await res.json();
    $("#scriptOut").value = data.error ? `生成失败：${data.error}` : data.script;
  } catch (err) {
    $("#scriptOut").value = "生成失败：" + err.message;
  }
}

function download(text, filename, type = "application/javascript;charset=utf-8") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function copyScript() {
  const text = $("#scriptOut").value;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    $("#scriptOut").select();
    document.execCommand("copy");
  }
  const btn = $("#copyScript");
  btn.textContent = "已复制";
  setTimeout(() => (btn.textContent = "复制"), 1200);
}

// ---------------------------------------------------------------- 加载歌单
let loading = false;

function showProgress(text, percent, isError = false) {
  $("#progress").hidden = false;
  $("#progress").classList.toggle("error", isError);
  $("#bar").style.width = `${Math.max(0, Math.min(100, percent))}%`;
  $("#progressText").textContent = text;
}

function hideProgress() {
  $("#progress").hidden = true;
}

function setBusy(busy) {
  loading = busy;
  $("#loadBtn").disabled = busy;
  $("#loadBtn").textContent = busy ? "加载中…" : "加载歌单";
}

async function startLoad() {
  if (loading) return;
  const ref = $("#playlistUrl").value.trim();
  if (!ref) return alert("先粘贴歌单链接或 id");
  setBusy(true);
  showProgress("正在创建任务…", 0);
  try {
    const res = await fetch("/api/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ playlist: ref }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "加载失败");
    await pollJob(data.job);
  } catch (err) {
    showProgress("失败：" + err.message, 0, true);
  } finally {
    setBusy(false);
  }
}

function pollJob(id) {
  return new Promise((resolve) => {
    const timer = setInterval(async () => {
      let job;
      try {
        job = await (await fetch("/api/job?id=" + id)).json();
      } catch {
        return; // 抖动一次不致命
      }
      const percent = job.total ? (job.progress / job.total) * 100 : 0;
      showProgress(`${job.message}（${Math.round(percent)}%）`, percent);
      if (job.status === "done") {
        clearInterval(timer);
        showProgress(job.message, 100);
        await reloadData();
        setTimeout(hideProgress, 3000);
        resolve();
      } else if (job.status === "error") {
        clearInterval(timer);
        showProgress("失败：" + job.message, 0, true);
        resolve();
      }
    }, 800);
  });
}

async function reloadData() {
  state.langs.clear();
  state.genres.clear();
  state.selected.clear();
  state.q = "";
  state.review = false;
  state.page = 0;
  $("#q").value = "";
  $("#reviewOnly").checked = false;
  await boot();
}

// ---------------------------------------------------------------- 绑定
$("#q").addEventListener("input", (event) => {
  state.q = event.target.value.trim().toLowerCase();
  state.page = 0;
  render();
});
$("#reviewOnly").addEventListener("change", (event) => {
  state.review = event.target.checked;
  state.page = 0;
  render();
});
$("#reset").addEventListener("click", () => {
  state.langs.clear();
  state.genres.clear();
  state.q = "";
  state.review = false;
  state.page = 0;
  $("#q").value = "";
  $("#reviewOnly").checked = false;
  renderChips();
  render();
});
$("#selectAll").addEventListener("click", selectAllFiltered);
$("#clearSel").addEventListener("click", clearSelection);
$("#exportCsv").addEventListener("click", exportCsv);
$("#makeScript").addEventListener("click", makeScript);
$("#prev").addEventListener("click", () => {
  state.page = Math.max(0, state.page - 1);
  render();
});
$("#next").addEventListener("click", () => {
  state.page += 1;
  render();
});
$("#playlistName").addEventListener("input", () => {
  clearTimeout(window.__regenTimer);
  window.__regenTimer = setTimeout(() => regenerate(), 350);
});
$("#copyScript").addEventListener("click", copyScript);
$("#directWrite").addEventListener("click", directWrite);
$("#downloadScript").addEventListener("click", () => {
  download($("#scriptOut").value, `加歌单_${$("#playlistName").value.trim() || "自定义"}.js`);
});
$("#closeModal").addEventListener("click", () => $("#modal").close());
$("#loadBtn").addEventListener("click", startLoad);
$("#playlistUrl").addEventListener("keydown", (event) => {
  if (event.key === "Enter") startLoad();
});

// 第一次访问自动展开教程，之后记住收起状态
const tutorial = $("#tutorial");
if (tutorial) {
  if (!localStorage.getItem("tutorialSeen")) tutorial.open = true;
  tutorial.addEventListener("toggle", () => {
    if (!tutorial.open) localStorage.setItem("tutorialSeen", "1");
  });
}

boot();

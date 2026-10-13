// 릴스 A+B=C — 모든 데이터는 이 브라우저(localStorage)에만 저장된다.
const KEY = "reels-abc:v1";
const SECTIONS = ["hook", "body", "cta"];
const SECTION_KO = { hook: "후킹", body: "본문", cta: "CTA" };

// 마지막 행동 요청
const CTA_ASK_RE = /(팔로우|팔로잉|저장|댓글|공유|프로필|링크|디엠|DM|구독|좋아요|알림|적어|남겨|눌러|신청|구매|follow|save|comment|share|link in bio)/i;
// 행동 요청 앞에 붙는 예고/미끼 문장 (예: "이 외에도 ~ ETF들", "다 정리했으니까")
const CTA_BRIDGE_RE = /(이 ?외에도|그 ?외에도|나머지|더 많은|더 자세한|전부|다 정리|정리해|정리했|정리한|모아|보내|드릴게|드려요|줄게|궁금하|원하|받고 ?싶|필요하|알고 ?싶)/;
const CONNECTIVE_END_RE = /(니까|으니|면|는데|해서|려면|도록)\s*[.,!]?$/;
// 본문 안에서 새 섹션이 시작되는 표시
const SECTION_START_RE = /^(첫\s?번째|두\s?번째|세\s?번째|네\s?번째|다섯\s?번째|여섯\s?번째|첫째|둘째|셋째|넷째|다섯째|\d+\s*(번|위|등|단계|\.|\))|다음(은|으로)|마지막(으로|은)|또\s?하나|반대로|그런데|하지만|결론|정리하면|주의|단점|장점)/;

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const fmtNum = (n) => {
  if (n == null) return "";
  const unit = (v, u) => (v < 10 ? v.toFixed(1).replace(/\.0$/, "") : Math.round(v).toLocaleString("ko-KR")) + u;
  return n >= 1e8 ? unit(n / 1e8, "억") : n >= 1e4 ? unit(n / 1e4, "만") : n.toLocaleString("ko-KR");
};
function statsHtml(st) {
  if (!st) return "";
  const parts = [];
  if (st.views != null) parts.push(`<span title="조회수">▶ ${fmtNum(st.views)}</span>`);
  if (st.likes != null) parts.push(`<span title="좋아요">♥ ${fmtNum(st.likes)}</span>`);
  if (st.comments != null) parts.push(`<span title="댓글">💬 ${fmtNum(st.comments)}</span>`);
  return parts.length ? `<span class="stats">${parts.join("")}</span>` : "";
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const uid = () => Math.random().toString(36).slice(2, 10);
const GROUP_COLORS = ["#ff6a3d", "#16a37a", "#8b5cf6", "#2f80ed", "#e0457b", "#0ea5b7", "#c08a00", "#64748b"];
const gColor = (g) => GROUP_COLORS[(g.charCodeAt(0) - 65) % GROUP_COLORS.length];
const nextGroup = () => "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").find((l) => !state.groups.includes(l));

const LOCAL_URL = "http://127.0.0.1:8765";
const IS_LOCAL = ["127.0.0.1", "localhost"].includes(location.hostname);
let state = load();
let helper = { ok: false, ai: false };
let cDirty = false;
const loading = {}; // 그룹별 추출 중 표시

function load() {
  let s = null;
  try { s = JSON.parse(localStorage.getItem(KEY)); } catch {}
  return normalize(s);
}
function normalize(s) {
  const fallback = { groups: ["A", "B"], refs: [], picks: [], saved: [], settings: { helper: "http://127.0.0.1:8765", model: "auto", language: "ko", cookies: "" } };
  if (!s || !Array.isArray(s.refs)) return fallback;
  s = { ...fallback, ...s, settings: { ...fallback.settings, ...(s.settings || {}) } };
  for (const r of s.refs) {
    r.units.forEach((u) => (u.id ||= uid()));
    if (!r.sectioned) { autoSections(r.units); r.sectioned = true; }
    if (/^Video by /i.test(r.title || "") && r.uploader) r.title = niceTitle(r);
  }
  s.picks = (s.picks || []).filter((p) => typeof p === "object" && p && p.u);
  if (s.settings.model === "large-v3" && !s.settings.modelChosen) s.settings.model = "auto"; // 예전 기본값 → 자동
  s.groups = [...new Set([...(s.groups || ["A", "B"]), ...s.refs.map((r) => r.group)])].sort();
  return s;
}
const hasData = (s) => !!(s && ((s.refs && s.refs.length) || (s.saved && s.saved.length)));
let serverReady = false; // 컴퓨터 파일의 데이터를 먼저 불러온 뒤에만 덮어씀
function save() {
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch {}
  if (!IS_LOCAL || !serverReady) return;
  clearTimeout(save._t);
  save._t = setTimeout(pushState, 400);
}
function pushState() {
  clearTimeout(save._t);
  return fetch(`${location.origin}/api/state`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state) }).catch(() => {});
}
// 창을 닫을 때 마지막 변경까지 저장
window.addEventListener("pagehide", () => {
  if (IS_LOCAL && serverReady && save._t) { clearTimeout(save._t); navigator.sendBeacon(`${location.origin}/api/state`, JSON.stringify(state)); }
});

// ---- 확인·입력 창 (프로그램 창에서도 동작하는 자체 대화상자) ----
function ask(message, { input = false, value = "", ok = "확인", cancel = "취소", danger = false } = {}) {
  return new Promise((resolve) => {
    const wrap = document.createElement("div");
    wrap.className = "modal-wrap";
    wrap.innerHTML = `<div class="modal" role="dialog" aria-modal="true">
      <p class="modal-msg">${esc(message)}</p>
      ${input ? `<input class="modal-input" value="${esc(value)}">` : ""}
      <div class="modal-btns"><button data-r="0">${cancel}</button><button class="primary ${danger ? "danger-btn" : ""}" data-r="1">${ok}</button></div>
    </div>`;
    document.body.appendChild(wrap);
    const inp = $(".modal-input", wrap);
    (inp || $("[data-r='1']", wrap)).focus();
    if (inp) inp.select();
    const done = (yes) => { wrap.remove(); resolve(input ? (yes ? inp.value : null) : yes); };
    wrap.addEventListener("click", (e) => { if (e.target === wrap) done(false); const r = e.target.dataset.r; if (r) done(r === "1"); });
    wrap.addEventListener("keydown", (e) => { if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); });
  });
}
const isAppWindow = () => !!window.pywebview;
function openExternal(url) {
  if (isAppWindow()) api("/api/open", { url }).catch(() => {});
  else window.open(url, "_blank", "noopener");
}
function toast(msg, ms = 2400) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), ms);
}

// ------------------------------------------------------------ 추출기(로컬 헬퍼) API
async function api(path, body) {
  const opts = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const res = await fetch(state.settings.helper.replace(/\/$/, "") + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `추출기 오류 (${res.status})`);
  return data;
}

async function checkHelper() {
  const el = $("#helperStatus");
  try {
    helper = await api("/api/health");
    el.className = "status ok";
    el.textContent = "추출기 켜짐";
    el.title = `${helper.engine} · ${helper.model}`;
  } catch (e) {
    helper = { ok: false, ai: false, error: e.message };
    el.className = "status bad";
    el.textContent = "추출기 꺼짐";
    el.title = e.message;
  }
  $("#setupBanner").classList.toggle("hidden", helper.ok);
  renderSetup();
  $("#aiNote").textContent = helper.ai ? "고른 문장의 구조는 살리고 내용은 내 주제로 바꿔 써줘요." : "추출기에 ANTHROPIC_API_KEY를 넣으면 쓸 수 있어요.";
  $("#aiComposeBtn").disabled = !helper.ai;
}

// ------------------------------------------------------------ 문장 나누기 & 자동 구간 나누기
function segmentsToUnits(segments) {
  const units = [];
  for (const s of segments) {
    const parts = s.text.split(/(?<=[.!?。？！~…])\s+/).map((p) => p.trim()).filter(Boolean);
    const total = parts.reduce((n, p) => n + p.length, 0) || 1;
    let cursor = s.start ?? null;
    for (const p of parts) {
      units.push({ id: uid(), t: cursor, text: p, label: "body" });
      if (cursor != null && s.end != null) cursor += ((s.end - s.start) * p.length) / total;
    }
  }
  return units;
}

function heuristicSplit(units) {
  const n = units.length;
  if (!n) return;
  // CTA: 마지막 4줄 안에서 행동 요청을 찾고, 그 앞의 예고/연결 문장까지 거슬러 올라가 포함
  let ctaStart = n;
  for (let i = n - 1; i >= Math.max(0, n - 4); i--) {
    if (CTA_ASK_RE.test(units[i].text)) { ctaStart = i; break; }
  }
  if (ctaStart < n) {
    let back = 0;
    while (ctaStart > 1 && back < 3) {
      const prev = units[ctaStart - 1].text;
      if (CTA_BRIDGE_RE.test(prev) || CONNECTIVE_END_RE.test(prev)) { ctaStart--; back++; } else break;
    }
  }
  // 후킹: 첫 문장 + (앞 문장이 짧거나 이어지는 말이거나 3.5초 이내면) 다음 문장까지, 최대 3줄.
  // 본문 섹션 시작 표시("첫 번째는" 등)가 나오면 거기서 멈춤
  let hookEnd = 1;
  while (hookEnd < Math.min(3, ctaStart) && !SECTION_START_RE.test(units[hookEnd].text)) {
    const prev = units[hookEnd - 1].text;
    if (prev.length < 12 || CONNECTIVE_END_RE.test(prev) || (units[hookEnd].t ?? 99) < 3.5) hookEnd++;
    else break;
  }
  hookEnd = Math.min(hookEnd, Math.max(1, ctaStart));
  units.forEach((u, i) => { u.label = i < hookEnd ? "hook" : i >= ctaStart ? "cta" : "body"; });
  autoSections(units);
}

function autoSections(units) {
  let first = true;
  for (const u of units) {
    if (u.label !== "body") { u.brk = false; continue; }
    u.brk = first || SECTION_START_RE.test(u.text);
    if (u.brk && !first) u.stitle = "";
    first = false;
  }
}

// 블록 구성: 후킹 / 본문 섹션 1..n / CTA
function blocksOf(ref) {
  const hook = [], cta = [], body = [];
  for (const u of ref.units) {
    if (u.label === "hook") hook.push(u);
    else if (u.label === "cta") cta.push(u);
    else {
      if (!body.length || u.brk) body.push({ title: u.stitle || "", units: [] });
      body[body.length - 1].units.push(u);
    }
  }
  return { hook, body, cta };
}

function unitInfo(refId, unitId) {
  const ref = state.refs.find((r) => r.id === refId);
  if (!ref) return null;
  const u = ref.units.find((x) => x.id === unitId);
  if (!u) return null;
  let sec = 0, stitle = "";
  if (u.label === "body") {
    blocksOf(ref).body.forEach((b, i) => { if (b.units.includes(u)) { sec = i + 1; stitle = b.title; } });
  }
  return { ref, u, sec, stitle };
}

// ------------------------------------------------------------ 레퍼런스 추가
async function addFromUrl(group, url, form) {
  loading[group] = { started: Date.now(), url, error: null, stage: "download" };
  renderColumn(group);
  const tick = setInterval(async () => {
    try {
      const r = await (await fetch(`${state.settings.helper.replace(/\/$/, "")}/api/progress?url=${encodeURIComponent(url)}`)).json();
      if (loading[group] && r.stage) loading[group].stage = r.stage;
    } catch {}
    renderLoading(group);
  }, 1000);
  try {
    const r = await api("/api/transcribe", {
      url, model: state.settings.model, language: state.settings.language, cookies_from_browser: state.settings.cookies,
    });
    const ref = {
      id: uid(), group, url, title: r.screen_title || niceTitle(r), author: authorOf(r.uploader), uploader: r.uploader,
      duration: r.duration, caption: r.caption, model: r.model, stats: r.stats, video: r.video, v2: true, units: segmentsToUnits(r.segments), createdAt: Date.now(), sectioned: true,
    };
    if (!ref.units.length) throw new Error("말소리를 찾지 못했어요. 음악만 있는 영상일 수 있어요.");
    heuristicSplit(ref.units);
    state.refs.unshift(ref);
    save();
    loading[group] = null;
    renderColumn(group);
    toast(`${group}에 추가했어요`);
    if (helper.ai) autoSplit(ref.id);
  } catch (err) {
    const m = err.message;
    const msg = m.includes("Failed to fetch") ? "추출기가 꺼져 있어요. 프로그램을 껐다 켜거나, 설정 탭의 설치 명령을 다시 실행해 주세요."
      : /login|로그인|cookie/i.test(m) ? "인스타가 로그인을 요구해요. 설정 → '인스타가 막을 때: 로그인된 브라우저'를 골라주세요."
      : /private|비공개|not available|unavailable/i.test(m) ? "비공개이거나 삭제된 영상이에요."
      : /Unsupported URL|올바른 링크/i.test(m) ? "릴스·쇼츠·틱톡 링크가 맞는지 확인해 주세요."
      : /timed out|timeout|Network|연결/i.test(m) ? "인터넷 연결이 불안정해요. 잠시 후 다시 시도해 주세요."
      : m.split("\n")[0];
    loading[group] = { ...loading[group], error: msg };
    renderColumn(group);
  } finally {
    clearInterval(tick);
  }
}

async function backfillStats() {
  for (const ref of state.refs) {
    if (!ref.url || ref.v2) continue;
    ref.v2 = true;
    ref.author ||= authorOf(ref.uploader);
    try {
      const r = await api("/api/meta", { url: ref.url, cookies_from_browser: state.settings.cookies });
      ref.stats = r.stats;
    } catch {}
    try {
      const t = await api("/api/title", { url: ref.url, cookies_from_browser: state.settings.cookies, transcript: ref.units.map((u) => u.text).join(" ") });
      if (t.screen_title) ref.title = t.screen_title;
      ref.video = t.video;
    } catch {}
    save(); renderColumn(ref.group);
  }
}

const authorOf = (u) => (u || "").split("|")[0].trim();

function niceTitle(r) {
  const t = (r.title || "").trim();
  if (t && !/^Video by /i.test(t)) return t;
  return r.uploader ? `${r.uploader.split("|")[0].trim()}님 릴스` : t || "제목 없음";
}

// ------------------------------------------------------------ 레퍼런스 열 (A, B, C, D …)
function colHtml(g) {
  const n = state.refs.filter((r) => r.group === g).length;
  return `
    <div class="col" data-group="${g}" style="--g:${gColor(g)}">
      <div class="col-head">
        <span class="badge" style="background:var(--g)">${g}</span>
        <b>레퍼런스 ${g}</b>
        <span class="cnt">${n ? n + "개" : ""}</span>
        <button class="more" data-act="cmenu" data-group="${g}" aria-label="열 메뉴">⋯</button>
      </div>
      <form class="add" data-group="${g}">
        <input type="text" inputmode="url" placeholder="${g} 릴스 링크 붙여넣기 (여러 개도 OK)" required>
        <button type="submit" class="primary">가져오기</button>
      </form>
      <div class="manual hidden">
        <textarea rows="5" placeholder="대본을 한 줄에 한 문장씩 붙여넣으세요"></textarea>
        <div class="row"><button type="button" class="primary" data-act="manual-add">추가</button><button type="button" data-act="manual-close">취소</button></div>
      </div>
      <div class="refs" id="refs${g}"></div>
    </div>`;
}

function renderCols() {
  const cols = $("#cols");
  const next = nextGroup();
  cols.style.gridTemplateColumns = `repeat(${state.groups.length}, minmax(320px, 1fr))${next ? " 64px" : ""}`;
  cols.innerHTML = state.groups.map(colHtml).join("") +
    (next ? `<button class="add-col" data-act="add-col" title="레퍼런스 ${next} 열 추가"><span>+</span><small>${next} 추가</small></button>` : "");
  state.groups.forEach(renderColumn);
}

function updateColCount(g) {
  const el = $(`.col[data-group="${g}"] .cnt`);
  if (el) { const n = state.refs.filter((r) => r.group === g).length; el.textContent = n ? n + "개" : ""; }
}

const colsEl = $("#cols");
colsEl.addEventListener("submit", (e) => {
  const form = e.target.closest("form.add");
  if (!form) return;
  e.preventDefault();
  const input = $("input", form);
  const urls = (input.value.match(/https?:\/\/[^\s,]+/g) || []);
  if (!urls.length) { toast("릴스 링크(https://…)를 붙여넣어 주세요"); return; }
  input.value = "";
  enqueue(form.dataset.group, urls, form);
});
// 여러 링크는 하나씩 차례로 가져옴
const queues = {};
async function enqueue(group, urls, form) {
  const q = (queues[group] ||= { list: [], running: false });
  q.list.push(...urls);
  if (q.running) { toast(`${urls.length}개를 대기열에 넣었어요`); renderColumn(group); return; }
  q.running = true;
  while (q.list.length) {
    const url = q.list.shift();
    await addFromUrl(group, url, form);
  }
  q.running = false;
  renderColumn(group);
}
// 링크를 붙여넣으면 바로 가져오기
colsEl.addEventListener("paste", (e) => {
  const form = e.target.closest("form.add");
  if (!form) return;
  setTimeout(() => { if (/^https?:\/\//.test($("input", form).value.trim())) form.requestSubmit(); }, 0);
});
colsEl.addEventListener("click", (e) => {
  const act = e.target.closest("[data-act]")?.dataset.act;
  const col = e.target.closest(".col");
  if (act === "add-col") {
    const g = nextGroup();
    state.groups.push(g);
    save(); renderCols();
    const el = $(`.col[data-group="${g}"]`);
    el.scrollIntoView({ behavior: "smooth", inline: "end", block: "nearest" });
    $("input", el).focus();
    return;
  }
  if (!col) return;
  const g = col.dataset.group;
  const box = $(".manual", col);
  if (act === "manual-open") {
    box.classList.remove("hidden"); $("textarea", box).focus();
  } else if (act === "manual-close") {
    box.classList.add("hidden");
  } else if (act === "manual-add") {
    const ta = $("textarea", box);
    const lines = ta.value.split(/\n+/).map((l) => l.trim()).filter(Boolean);
    if (!lines.length) return toast("대본을 입력해 주세요");
    const ref = { id: uid(), group: g, url: "", title: lines[0].slice(0, 30), units: lines.map((text) => ({ id: uid(), t: null, text, label: "body" })), createdAt: Date.now(), sectioned: true };
    heuristicSplit(ref.units);
    state.refs.unshift(ref);
    save();
    ta.value = "";
    box.classList.add("hidden");
    renderColumn(g);
    if (helper.ai) autoSplit(ref.id);
  } else if (act === "cmenu") {
    const n = state.refs.filter((r) => r.group === g).length;
    openMenu(e.target.closest("[data-act]"), [
      { label: "✎ 링크 대신 대본 직접 넣기", run: () => { box.classList.remove("hidden"); $("textarea", box).focus(); } },
      "-",
      ...Object.entries(SORTS).map(([k, label]) => ({
        label: `${(state.sortBy || "recent") === k ? "✓" : "\u2003"} ${label}`,
        run: () => { state.sortBy = k; save(); state.groups.forEach(renderColumn); },
      })),
      "-",
      state.groups.length > 1 && { label: `레퍼런스 ${g} 열 삭제`, danger: true, run: async () => {
        if (n && !(await ask(`레퍼런스 ${g}에 있는 ${n}개도 함께 삭제돼요. 계속할까요?`, { ok: "삭제", danger: true }))) return;
        state.refs = state.refs.filter((r) => r.group !== g);
        state.groups = state.groups.filter((x) => x !== g);
        cleanPicks(); save(); renderCols(); recombine();
      } },
      state.groups.length <= 1 && { label: "마지막 열은 지울 수 없어요", run: () => {} },
    ]);
  }
});

async function autoSplit(id) {
  const ref = state.refs.find((r) => r.id === id);
  if (!ref) return;
  if (!helper.ai) {
    heuristicSplit(ref.units);
    save(); renderBoard();
    return toast("다시 나눴어요");
  }
  ref.busy = true; renderColumn(ref.group);
  try {
    const r = await api("/api/split", { segments: ref.units.map((u) => ({ text: u.text })) });
    r.units.forEach((x, i) => {
      const u = ref.units[i];
      if (!u) return;
      u.label = x.label;
      u.brk = x.label === "body" && x.section_start;
      u.stitle = u.brk ? x.section_title : "";
    });
    const firstBody = ref.units.find((u) => u.label === "body");
    if (firstBody) firstBody.brk = true;
    toast("AI가 후킹·본문·CTA를 나눴어요");
  } catch (e) {
    toast("AI 나누기 실패: " + e.message, 4000);
  } finally {
    delete ref.busy;
    save(); renderBoard();
  }
}

// ------------------------------------------------------------ 화면 그리기
const isPicked = (refId, uId) => state.picks.some((p) => p.r === refId && p.u === uId);
const orderOf = (refId, uId) => orderNo.get(`${refId}:${uId}`) || 0;

function unitRow(ref, u) {
  const n = orderOf(ref.id, u.id) - 1;
  return `
    <div class="unit ${n >= 0 ? "on" : ""}" data-u="${u.id}">
      <span class="chk">${n >= 0 ? n + 1 : ""}</span>
      <span class="txt" spellcheck="false">${esc(u.text)}</span>
      ${ref.url && u.t != null ? `<button class="play" data-act="play" title="원본 영상에서 이 부분 보기" aria-label="원본 보기">▶</button>` : ""}
      <button class="more" data-act="umenu" aria-label="문장 메뉴">⋯</button>
    </div>`;
}

function blockHtml(ref, kind, units, { title, idx = 0, sectionTitle = "" }) {
  const allOn = units.every((u) => isPicked(ref.id, u.id));
  return `
    <div class="blk ${kind}">
      <div class="bh">
        <span class="bt">${title}${sectionTitle ? ` <span class="st">· ${esc(sectionTitle)}</span>` : ""}</span>
        <button class="pick-all" data-act="selblk" data-ids="${units.map((u) => u.id).join(",")}">${allOn ? "✓ 다 골랐어요" : "통째로 고르기"}</button>
        ${kind === "body" ? `<button class="more" data-act="smenu" data-u="${units[0].id}" data-idx="${idx}" aria-label="섹션 메뉴">⋯</button>` : ""}
      </div>
      ${units.map((u) => unitRow(ref, u)).join("")}
    </div>`;
}

function refCard(ref) {
  const { hook, body, cta } = blocksOf(ref);
  const picked = ref.units.filter((u) => isPicked(ref.id, u.id)).length;
  return `
    <article class="ref ${ref.folded ? "folded" : ""}" data-id="${ref.id}">
      <div class="ref-head" data-act="fold">
        <span class="caret">${ref.folded ? "▸" : "▾"}</span>
        <div class="meta">
          <div class="title">${esc(ref.title)}</div>
          ${ref.author ? `<div class="author">${esc(ref.author)}</div>` : ""}
          <div class="sub">${statsHtml(ref.stats)}<span class="subtxt">${ref.busy ? "AI가 나누는 중…" : `${ref.units.length}문장${picked ? ` · <b>${picked}개 고름</b>` : ""}`}</span></div>
        </div>
        <button class="more" data-act="rmenu" aria-label="레퍼런스 메뉴">⋯</button>
      </div>
      ${ref.folded ? "" : `
      ${hook.length ? blockHtml(ref, "hook", hook, { title: "후킹" }) : ""}
      ${body.map((b, i) => blockHtml(ref, "body", b.units, { title: body.length > 1 ? `본문 ${i + 1}` : "본문", idx: i, sectionTitle: b.title })).join("")}
      ${cta.length ? blockHtml(ref, "cta", cta, { title: "CTA" }) : ""}`}
    </article>`;
}

function loadingHtml(group) {
  const l = loading[group];
  if (!l) return "";
  if (l.error) return `<div class="loading err"><b>가져오지 못했어요</b><p>${esc(l.error)}</p><button class="link" data-act="dismiss" data-group="${group}">닫기</button></div>`;
  const s = Math.round((Date.now() - l.started) / 1000);
  const waiting = queues[group]?.list.length || 0;
  return `<div class="loading"><div class="steps-live">${stepsHtml(l.stage)}</div>
    <p class="sec-line"><span class="sec">${s}초</span>${waiting ? ` · 대기 ${waiting}개` : ""}</p></div>`;
}
const STAGES = [["download", "영상 받기"], ["transcribe", "대본 받아쓰기"], ["title", "타이틀 자막 읽기"], ["stats", "조회수 확인"]];
function stepsHtml(stage) {
  const cur = Math.max(0, STAGES.findIndex(([k]) => k === stage));
  return STAGES.map(([, label], i) =>
    `<div class="st-row ${i < cur ? "done" : i === cur ? "now" : ""}"><span class="st-dot">${i < cur ? "✓" : i === cur ? '<span class="spin"></span>' : ""}</span>${label}</div>`).join("");
}
function renderLoading(group) {
  const box = $(`#refs${group} .loading .steps-live`);
  if (box && loading[group] && !loading[group].error) box.innerHTML = stepsHtml(loading[group].stage);
  const el = $(`#refs${group} .loading .sec`);
  if (el && loading[group]) el.textContent = `${Math.round((Date.now() - loading[group].started) / 1000)}초`;
}

const SORTS = { recent: "최근 추가순", views: "조회수 높은 순", likes: "좋아요 많은 순", comments: "댓글 많은 순" };
function sortRefs(refs) {
  const k = state.sortBy || "recent";
  if (k === "recent") return refs;
  return [...refs].sort((a, b) => (b.stats?.[k] ?? -1) - (a.stats?.[k] ?? -1));
}

function renderColumn(g) {
  computeOrder();
  const el = $("#refs" + g);
  if (!el) return;
  const refs = sortRefs(state.refs.filter((r) => r.group === g));
  el.innerHTML = loadingHtml(g) + (refs.length ? refs.map(refCard).join("")
    : loading[g] ? "" : `<div class="empty-state"><div class="big-badge" style="--g:${gColor(g)}">${g}</div><p>릴스 링크를 붙여넣으면<br>대본이 여기에 나와요</p></div>`);
  updateColCount(g);
}

function renderBoard() {
  if ($$(".col").length !== state.groups.length) renderCols();
  else state.groups.forEach(renderColumn);
  renderC();
}

// 선택 상태만 제자리에서 갱신 (다시 그리지 않아야 더블클릭 수정이 살아 있음)
function refreshSelection() {
  computeOrder();
  $$(".ref").forEach((card) => {
    const rid = card.dataset.id;
    $$(".unit", card).forEach((row) => {
      const n = orderOf(rid, row.dataset.u) - 1;
      row.classList.toggle("on", n >= 0);
      $(".chk", row).textContent = n >= 0 ? n + 1 : "";
    });
    $$("[data-act=selblk]", card).forEach((b) => {
      const allOn = b.dataset.ids.split(",").every((id) => isPicked(rid, id));
      b.textContent = allOn ? "✓ 다 골랐어요" : "통째로 고르기";
    });
    const ref = state.refs.find((r) => r.id === rid);
    const picked = ref.units.filter((u) => isPicked(rid, u.id)).length;
    const sub = $(".subtxt", card);
    if (sub && !ref.busy) sub.innerHTML = `${ref.units.length}문장${picked ? ` · <b>${picked}개 고름</b>` : ""}`;
  });
  renderC();
}

function cleanPicks() {
  state.picks = state.picks.filter((p) => unitInfo(p.r, p.u));
}
function togglePick(refId, uId) {
  if (isPicked(refId, uId)) state.picks = state.picks.filter((p) => !(p.r === refId && p.u === uId));
  else state.picks.push({ r: refId, u: uId });
  save(); refreshSelection(); recombine();
}

// ------------------------------------------------------------ 메뉴 (⋯)
const menu = $("#menu");
let menuActions = [];
function openMenu(anchor, items) {
  menuActions = items.filter(Boolean);
  menu.innerHTML = menuActions.map((it, i) => it === "-" ? `<hr>` : `<button data-i="${i}" class="${it.danger ? "danger" : ""}">${it.label}</button>`).join("");
  menu.classList.remove("hidden");
  const r = anchor.getBoundingClientRect();
  const w = menu.offsetWidth, h = menu.offsetHeight;
  menu.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.right - w)) + "px";
  menu.style.top = (r.bottom + h + 8 > window.innerHeight ? r.top - h - 4 : r.bottom + 4) + "px";
}
function closeMenu() { menu.classList.add("hidden"); }
menu.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-i]");
  if (!b) return;
  closeMenu();
  menuActions[+b.dataset.i].run();
});
document.addEventListener("click", (e) => { if (!e.target.closest("#menu, [data-act$=menu]")) closeMenu(); });
window.addEventListener("scroll", closeMenu, true);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });

function startEdit(el) {
  el.contentEditable = "true";
  el.focus();
  const range = document.createRange();
  range.selectNodeContents(el);
  range.collapse(false);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
}

function unitMenu(ref, u, anchor) {
  const blocks = blocksOf(ref);
  const firstInSection = blocks.body.some((b) => b.units[0] === u);
  const move = (label) => () => {
    u.label = label;
    if (label === "body") u.brk = !ref.units.some((x) => x !== u && x.label === "body") || u.brk;
    save(); renderBoard(); recombine();
  };
  openMenu(anchor, [
    { label: "✏️ 문장 고치기", run: () => startEdit($(`.ref[data-id="${ref.id}"] .unit[data-u="${u.id}"] .txt`)) },
    u.label === "body" && !firstInSection && { label: "✂️ 여기서부터 새 본문 섹션", run: () => { u.brk = true; save(); renderBoard(); } },
    "-",
    u.label !== "hook" && { label: "후킹으로 옮기기", run: move("hook") },
    u.label !== "body" && { label: "본문으로 옮기기", run: move("body") },
    u.label !== "cta" && { label: "CTA로 옮기기", run: move("cta") },
    "-",
    { label: "문장 지우기", danger: true, run: () => {
      const i = ref.units.indexOf(u);
      ref.units.splice(i, 1);
      if (u.brk && ref.units[i]?.label === "body") ref.units[i].brk = true;
      cleanPicks(); save(); renderBoard(); recombine();
    } },
  ]);
}

function sectionMenu(ref, u, idx, anchor) {
  openMenu(anchor, [
    { label: "🏷️ 섹션 이름 붙이기", run: async () => {
      const v = await ask("이 본문 섹션의 이름 (예: SMH 반도체)", { input: true, value: u.stitle || "", ok: "저장" });
      if (v === null) return;
      u.stitle = v.trim(); save(); renderBoard(); recombine();
    } },
    idx > 0 && { label: "↑ 위 섹션과 합치기", run: () => { u.brk = false; u.stitle = ""; save(); renderBoard(); recombine(); } },
  ]);
}

function refMenu(ref, anchor) {
  openMenu(anchor, [
    { label: "✏️ 제목 바꾸기", run: async () => {
      const v = await ask("제목", { input: true, value: ref.title, ok: "저장" });
      if (v && v.trim()) { ref.title = v.trim(); save(); renderBoard(); }
    } },
    { label: helper.ai ? "🤖 AI로 다시 나누기" : "↻ 자동으로 다시 나누기", run: () => autoSplit(ref.id) },
    { label: "📋 대본 전체 복사", run: () => {
      const { hook, body, cta } = blocksOf(ref);
      const txt = [
        hook.length && `[후킹]\n${hook.map((u) => u.text).join("\n")}`,
        ...body.map((b, i) => `[본문 ${i + 1}${b.title ? " · " + b.title : ""}]\n${b.units.map((u) => u.text).join("\n")}`),
        cta.length && `[CTA]\n${cta.map((u) => u.text).join("\n")}`,
      ].filter(Boolean).join("\n\n");
      navigator.clipboard.writeText(txt).then(() => toast("복사했어요"));
    } },
    ref.url && { label: "▶️ 인스타에서 원본 열기", run: () => openExternal(ref.url) },
    ...state.groups.filter((g) => g !== ref.group).map((g) => ({ label: `${g}로 옮기기`, run: () => { ref.group = g; save(); state.groups.forEach(renderColumn); renderC(); } })),
    "-",
    { label: "삭제", danger: true, run: async () => {
      if (!(await ask(`"${ref.title}"을(를) 삭제할까요?`, { ok: "삭제", danger: true }))) return;
      state.refs = state.refs.filter((r) => r.id !== ref.id);
      cleanPicks(); save(); renderBoard(); recombine();
    } },
  ]);
}

// ------------------------------------------------------------ 보드 이벤트
const board = $(".workspace");
board.addEventListener("click", (e) => {
  if (e.target.closest("[contenteditable=true]")) return;
  const dismiss = e.target.closest("[data-act=dismiss]");
  if (dismiss) { loading[dismiss.dataset.group] = null; renderColumn(dismiss.dataset.group); return; }
  const card = e.target.closest(".ref");
  if (!card) return;
  const ref = state.refs.find((r) => r.id === card.dataset.id);
  const actEl = e.target.closest("[data-act]");
  const act = actEl?.dataset.act;
  const row = e.target.closest(".unit");
  const u = row && ref.units.find((x) => x.id === row.dataset.u);

  if (act === "play") playUnit(ref, u);
  else if (act === "umenu") unitMenu(ref, u, actEl);
  else if (act === "smenu") sectionMenu(ref, ref.units.find((x) => x.id === actEl.dataset.u), +actEl.dataset.idx, actEl);
  else if (act === "rmenu") refMenu(ref, actEl);
  else if (act === "selblk") {
    const ids = actEl.dataset.ids.split(",");
    const allOn = ids.every((id) => isPicked(ref.id, id));
    if (allOn) state.picks = state.picks.filter((p) => !(p.r === ref.id && ids.includes(p.u)));
    else ids.forEach((id) => { if (!isPicked(ref.id, id)) state.picks.push({ r: ref.id, u: id }); });
    save(); refreshSelection(); recombine();
  } else if (act === "fold") {
    ref.folded = !ref.folded;
    save(); renderColumn(ref.group);
  } else if (row && lastPointer !== "mouse") togglePick(ref.id, u.id); // 터치는 탭으로 선택
});

// 마우스: 누르면 선택, 누른 채로 끌면 지나간 문장 모두 같은 상태로 (선택 ↔ 해제)
let drag = null;
let lastPointer = "mouse";
function dragApply(refId, uId) {
  const ref = state.refs.find((r) => r.id === refId);
  if (!ref) return;
  // 같은 카드 안에서는 건너뛴 줄까지 채움
  let ids = [uId];
  if (drag.last && drag.last.r === refId) {
    const a = ref.units.findIndex((x) => x.id === drag.last.u);
    const b = ref.units.findIndex((x) => x.id === uId);
    ids = (a <= b ? ref.units.slice(a, b + 1) : ref.units.slice(b, a + 1).reverse()).map((x) => x.id);
  }
  for (const id of ids) {
    const on = isPicked(refId, id);
    if (drag.mode && !on) state.picks.push({ r: refId, u: id });
    else if (!drag.mode && on) state.picks = state.picks.filter((p) => !(p.r === refId && p.u === id));
  }
  drag.last = { r: refId, u: uId };
  refreshSelection();
  recombine();
}
board.addEventListener("pointerdown", (e) => {
  lastPointer = e.pointerType;
  if (e.pointerType !== "mouse" || e.button !== 0) return;
  const row = e.target.closest(".unit");
  if (!row || e.target.closest("button, [contenteditable=true]")) return;
  e.preventDefault(); // 글자 드래그 선택 방지
  const refId = row.closest(".ref").dataset.id;
  drag = { mode: !isPicked(refId, row.dataset.u), last: null };
  document.body.classList.add("dragging");
  dragApply(refId, row.dataset.u);
});
document.addEventListener("pointermove", (e) => {
  if (!drag) return;
  // 화면 끝으로 끌면 자동 스크롤
  if (e.clientY > window.innerHeight - 50) window.scrollBy(0, 18);
  else if (e.clientY < 90) window.scrollBy(0, -18);
  const row = document.elementFromPoint(e.clientX, e.clientY)?.closest(".unit");
  if (!row) return;
  const refId = row.closest(".ref").dataset.id;
  if (drag.last && drag.last.r === refId && drag.last.u === row.dataset.u) return;
  dragApply(refId, row.dataset.u);
});
document.addEventListener("pointerup", () => {
  if (!drag) return;
  drag = null;
  document.body.classList.remove("dragging");
  save();
});

// 더블클릭으로도 문장 고치기
board.addEventListener("dblclick", (e) => {
  const el = e.target.closest(".unit .txt");
  if (!el) return;
  e.preventDefault();
  startEdit(el);
});
board.addEventListener("focusout", (e) => {
  const el = e.target;
  if (el.contentEditable !== "true") return;
  el.contentEditable = "false";
  const ref = state.refs.find((r) => r.id === el.closest(".ref").dataset.id);
  const i = ref.units.findIndex((x) => x.id === el.closest(".unit").dataset.u);
  const v = el.textContent.trim();
  if (!v) { ref.units.splice(i, 1); cleanPicks(); renderBoard(); }
  else ref.units[i].text = v;
  save(); recombine();
});
board.addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === "Escape") && e.target.isContentEditable) { e.preventDefault(); e.target.blur(); }
});

// ------------------------------------------------------------ 원본 영상 구간 재생
const player = { ref: null, end: null };
async function playUnit(ref, u) {
  const box = $("#player"), video = $("#playerVideo");
  box.classList.remove("hidden");
  $("#playerTitle").textContent = ref.title;
  $("#playerText").textContent = u.text;
  $$(".unit.playing").forEach((x) => x.classList.remove("playing"));
  $(`.ref[data-id="${ref.id}"] .unit[data-u="${u.id}"]`)?.classList.add("playing");
  // 이 문장 끝 = 다음 문장의 시작 시간
  const timed = ref.units.filter((x) => x.t != null);
  const next = timed[timed.indexOf(u) + 1];
  player.end = next ? next.t + 0.1 : null;
  const start = Math.max(0, u.t - 0.15);
  if (!ref.video) {
    box.classList.add("loading-video");
    try {
      const r = await api("/api/video", { url: ref.url, cookies_from_browser: state.settings.cookies });
      ref.video = r.src; save();
    } catch (e) {
      box.classList.remove("loading-video");
      $("#playerText").textContent = "원본 영상을 받지 못했어요: " + e.message.split("\n")[0];
      return;
    }
    box.classList.remove("loading-video");
  }
  const src = state.settings.helper.replace(/\/$/, "") + ref.video;
  if (player.ref !== ref.id || !video.src.endsWith(ref.video)) { video.src = src; player.ref = ref.id; }
  const go = () => { video.currentTime = start; video.play().catch(() => {}); };
  if (video.readyState >= 1) go(); else video.addEventListener("loadedmetadata", go, { once: true });
}
$("#playerVideo").addEventListener("timeupdate", (e) => {
  if (player.end != null && e.target.currentTime >= player.end) { e.target.pause(); player.end = null; }
});
$("#playerVideo").addEventListener("seeking", (e) => { if (!e.target.paused && player.end != null && e.target.currentTime > player.end) player.end = null; });
$("#playerClose").addEventListener("click", () => {
  $("#playerVideo").pause();
  $("#player").classList.add("hidden");
  $$(".unit.playing").forEach((x) => x.classList.remove("playing"));
});

// ------------------------------------------------------------ C 조합
// 대본 순서: 후킹 → 본문 → CTA.
// 같은 구간 안에서는 "먼저 고른 문단"이 앞에 오고, 한 문단 안의 문장은 클릭 순서와 상관없이 원래 문장 순서대로.
function pickedItems() {
  const raw = state.picks.map((p, clickNo) => {
    const info = unitInfo(p.r, p.u);
    return info && {
      ...p, clickNo, group: info.ref.group, title: info.ref.title, label: info.u.label, text: info.u.text,
      sec: info.sec, stitle: info.stitle, pos: info.ref.units.indexOf(info.u), block: `${p.r}:${info.u.label}:${info.sec}`,
    };
  }).filter(Boolean);
  // 문단 순서: 끌어서 정한 순서가 있으면 그대로, 없으면 먼저 고른 순
  const rank = new Map();
  for (const x of raw) {
    if (rank.has(x.block)) continue;
    const manual = (state.order?.[x.label] || []).indexOf(x.block);
    rank.set(x.block, manual >= 0 ? manual : 1e6 + x.clickNo);
  }
  return SECTIONS.flatMap((s) => raw.filter((x) => x.label === s)
    .sort((a, b) => rank.get(a.block) - rank.get(b.block) || a.pos - b.pos));
}

// 화면에 보이는 번호 = 완성 대본에서의 순서
let orderNo = new Map();
function computeOrder() {
  orderNo = new Map(pickedItems().map((x, i) => [`${x.r}:${x.u}`, i + 1]));
}

// 후킹 → 본문 → CTA 순으로, 각 구간 안에서는 고른 순서대로. 본문은 (레퍼런스, 섹션)이 바뀌면 빈 줄.
function composeText(items) {
  const out = [];
  for (const s of SECTIONS) {
    const list = items.filter((x) => x.label === s);
    if (!list.length) continue;
    const lines = [];
    let prevKey = null;
    for (const x of list) {
      const key = `${x.r}:${x.sec}`;
      if (s === "body" && prevKey && key !== prevKey) lines.push("");
      lines.push(x.text);
      prevKey = key;
    }
    out.push(`[${SECTION_KO[s]}]\n${lines.join("\n")}`);
  }
  return out.join("\n\n");
}

let prevChips = new Set();
function renderC() {
  const items = pickedItems();
  const nowChips = new Set(items.map((x) => `${x.r}:${x.u}`));
  $("#pickCount").textContent = items.length ? `${items.length}문장` : "";
  $("#toC").textContent = `내 대본 보기 (${items.length})`;
  $("#toC").classList.toggle("hidden", !items.length);
  $("#clearPicks").classList.toggle("hidden", !items.length);
  $("#cParts").innerHTML = items.length
    ? SECTIONS.map((sec) => {
        const list = items.filter((x) => x.label === sec);
        if (!list.length) return "";
        const blocks = [];
        for (const x of list) {
          let b = blocks.find((y) => y.key === x.block);
          if (!b) blocks.push(b = { key: x.block, x, lines: [] });
          b.lines.push(x);
        }
        return `<div class="mix-sec ${sec}"><div class="mix-label">${SECTION_KO[sec]}</div>
          <div class="blocks" data-label="${sec}">${blocks.map((b) => {
            const name = sec === "body" ? (b.x.stitle || `본문 ${b.x.sec}`) : SECTION_KO[sec];
            const isNew = b.lines.some((l) => !prevChips.has(`${l.r}:${l.u}`));
            return `<div class="cblock ${isNew ? "new" : ""}" draggable="${blocks.length > 1}" data-block="${b.key}" data-label="${sec}">
              ${blocks.length > 1 ? `<span class="grip" title="끌어서 순서 바꾸기">⠿</span>` : ""}
              <b class="g" style="background:${gColor(b.x.group)}">${b.x.group}</b>
              <div class="cb-main"><div class="cb-title">${esc(name)} <span>· ${b.lines.length}문장</span></div>
              <div class="cb-prev">${esc(b.lines[0].text)}</div></div>
              <button class="x" data-act="unpick-block" title="이 문단 빼기">✕</button>
            </div>`;
          }).join("")}</div></div>`;
      }).join("")
    : `<div class="c-empty"><div class="c-empty-icon">↖</div>레퍼런스에서 문장을 <b>클릭</b>하거나<br><b>드래그</b>해서 골라보세요</div>`;
  $("#recombine").classList.toggle("hidden", !cDirty || !items.length);
  prevChips = nowChips;
}

function recombine() {
  if (!cDirty) $("#cText").value = composeText(pickedItems());
  renderC();
}

$("#cParts").addEventListener("click", (e) => {
  if (e.target.dataset.act !== "unpick-block") return;
  const key = e.target.closest(".cblock").dataset.block;
  const ids = new Set(pickedItems().filter((x) => x.block === key).map((x) => `${x.r}:${x.u}`));
  state.picks = state.picks.filter((p) => !ids.has(`${p.r}:${p.u}`));
  save(); refreshSelection(); recombine();
});

// 문단 카드를 끌어서 순서 바꾸기 (같은 구간 안에서)
let dragBlock = null;
$("#cParts").addEventListener("dragstart", (e) => {
  dragBlock = e.target.closest(".cblock");
  if (!dragBlock) return;
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", dragBlock.dataset.block);
  requestAnimationFrame(() => dragBlock?.classList.add("dragging"));
});
$("#cParts").addEventListener("dragover", (e) => {
  if (!dragBlock) return;
  const list = e.target.closest(".blocks");
  if (!list || list.dataset.label !== dragBlock.dataset.label) return;
  e.preventDefault();
  const after = [...list.querySelectorAll(".cblock:not(.dragging)")].find((el) => {
    const r = el.getBoundingClientRect();
    return e.clientY < r.top + r.height / 2;
  });
  if (after) { if (after.previousElementSibling !== dragBlock) list.insertBefore(dragBlock, after); }
  else if (list.lastElementChild !== dragBlock) list.appendChild(dragBlock);
});
$("#cParts").addEventListener("dragend", () => {
  if (!dragBlock) return;
  const list = dragBlock.closest(".blocks");
  dragBlock.classList.remove("dragging");
  state.order = state.order || {};
  state.order[list.dataset.label] = [...list.querySelectorAll(".cblock")].map((el) => el.dataset.block);
  dragBlock = null;
  cDirty = false;
  save(); refreshSelection(); recombine();
});
$("#clearPicks").addEventListener("click", async () => {
  if (!(await ask("고른 문장을 모두 지울까요?", { ok: "지우기", danger: true }))) return;
  state.picks = [];
  cDirty = false;
  save(); refreshSelection(); recombine();
});
$("#cText").addEventListener("input", () => { cDirty = true; renderC(); });
$("#recombine").addEventListener("click", () => { cDirty = false; recombine(); });
$("#toC").addEventListener("click", () => $("#cpanel").scrollIntoView({ behavior: "smooth" }));

$("#aiComposeBtn").addEventListener("click", async () => {
  const items = pickedItems();
  if (!items.length) return toast("먼저 문장을 골라주세요");
  // 같은 (레퍼런스, 구간, 섹션)끼리 묶어서 재료로 보냄
  const parts = [];
  for (const x of items) {
    const last = parts[parts.length - 1];
    const key = `${x.r}:${x.label}:${x.sec}`;
    if (last && last.key === key) last.text += "\n" + x.text;
    else parts.push({ key, group: x.group, section: x.label, sectionTitle: x.label === "body" ? (x.stitle || `본문 ${x.sec}`) : "", title: x.title, text: x.text });
  }
  const btn = $("#aiComposeBtn");
  btn.disabled = true; btn.textContent = "AI가 쓰는 중…";
  try {
    const r = await api("/api/compose", { parts, topic: $("#topicInput").value, tone: $("#toneInput").value });
    $("#cText").value = `[후킹]\n${r.hook}\n\n[본문]\n${r.body}\n\n[CTA]\n${r.cta}` + (r.notes ? `\n\n---\n참고: ${r.notes}` : "");
    cDirty = true;
    renderC();
    if (!$("#cTitle").value && $("#topicInput").value) $("#cTitle").value = $("#topicInput").value;
  } catch (e) {
    toast("AI 쓰기 실패: " + e.message, 4000);
  } finally {
    btn.disabled = !helper.ai; btn.textContent = "AI로 다시 쓰기";
  }
});

$("#copyC").addEventListener("click", () => {
  const v = $("#cText").value.trim();
  if (!v) return toast("아직 대본이 비어 있어요");
  navigator.clipboard.writeText(v).then(() => toast("복사했어요"));
});
$("#saveC").addEventListener("click", () => {
  const text = $("#cText").value.trim();
  if (!text) return toast("아직 대본이 비어 있어요");
  const sources = [...new Set(pickedItems().map((x) => `${x.group}: ${x.title}`))];
  state.saved.unshift({ id: uid(), title: $("#cTitle").value.trim() || `대본 ${new Date().toLocaleDateString("ko-KR")}`, text, sources, createdAt: Date.now() });
  save();
  toast("보관함에 저장했어요");
});

// ------------------------------------------------------------ 보관함
function renderSaved() {
  $("#savedList").innerHTML = state.saved.length ? state.saved.map((c) => `
    <article class="card saved" data-id="${c.id}">
      <div class="saved-head"><b>${esc(c.title)}</b><span class="muted small">${new Date(c.createdAt).toLocaleDateString("ko-KR")}</span></div>
      <pre>${esc(c.text)}</pre>
      ${c.sources.length ? `<div class="src">재료: ${c.sources.map(esc).join(", ")}</div>` : ""}
      <div class="row"><button data-act="copy" class="primary">복사</button><button data-act="del" class="link danger">삭제</button></div>
    </article>`).join("") : `<div class="empty-state"><p>아직 보관한 대본이 없어요.<br>만들기 탭에서 대본을 만들고 "보관함에 저장"을 눌러보세요.</p></div>`;
}
$("#savedList").addEventListener("click", (e) => {
  const card = e.target.closest("[data-id]");
  const act = e.target.dataset.act;
  if (!card || !act) return;
  const c = state.saved.find((x) => x.id === card.dataset.id);
  if (act === "copy") navigator.clipboard.writeText(c.text).then(() => toast("복사했어요"));
  if (act === "del") ask("이 대본을 삭제할까요?", { ok: "삭제", danger: true }).then((y) => { if (y) { state.saved = state.saved.filter((x) => x !== c); save(); renderSaved(); } });
});

// ------------------------------------------------------------ 설정
function renderSettings() {
  $("#setHelper").value = state.settings.helper;
  $("#setModel").value = state.settings.model;
  $("#setLang").value = state.settings.language;
  $("#setCookies").value = state.settings.cookies;
  renderSetup();
}

// ------------------------------------------------------------ 추출기 설치 안내 (복사 → 붙여넣기 → Enter)
const SITE = location.hostname.endsWith("vercel.app") || location.protocol === "https:" ? location.origin : "https://reels-abc.vercel.app";
let setupOS = /Win/i.test(navigator.platform || navigator.userAgent) ? "win" : "mac";
const SETUP = {
  mac: {
    cmd: `curl -fsSL ${SITE}/install.sh | bash`,
    open: `<b>터미널 열기</b><br><span class="muted">⌘ Command + Space 누르고 "터미널" 입력 → Enter</span>`,
    paste: `<b>터미널에 붙여넣고 Enter</b><br><span class="muted">⌘ Command + V → Enter. "✅ 설치 끝!"이 나오면 프로그램이 열려요</span>`,
    uninstallHelp: "터미널에 붙여넣고 Enter 하면 프로그램이 지워져요. 만든 레퍼런스·대본은 남겨둬서, 다시 설치하면 그대로 나와요.",
    uninstall: `launchctl bootout gui/$(id -u)/app.reelsabc.helper; find ~/ReelsExtractor -mindepth 1 -maxdepth 1 ! -name data -exec rm -rf {} +; rm -rf ~/Library/LaunchAgents/app.reelsabc.helper.plist ~/Desktop/"릴스 A+B=C.webloc" ~/Desktop/"릴스 A+B=C" ~/Applications/"릴스 A+B=C.app"`,
  },
  win: {
    cmd: `powershell -NoExit -ExecutionPolicy Bypass -c "irm ${SITE}/install.ps1 | iex"`,
    open: `<b>키보드에서 <kbd>⊞ Windows</kbd> 키를 누른 채 <kbd>R</kbd></b><br><span class="muted">화면 왼쪽 아래에 작은 "실행" 창이 떠요</span>`,
    paste: `<b><kbd>Ctrl</kbd> + <kbd>V</kbd> 로 붙여넣고 <kbd>Enter</kbd></b><br><span class="muted">파란 창이 열리고 설치가 저절로 진행돼요 (5~15분). 필요한 건 전부 자동으로 깔려요.<br>"확인 창"이 뜨면 [예] · "설치 끝!"이 나오면 프로그램이 열려요</span>`,
    uninstallHelp: "Windows 키 + R → powershell 입력 → 열린 창에 붙여넣고 Enter 하면 프로그램이 지워져요. 만든 레퍼런스·대본은 남겨둬서, 다시 설치하면 그대로 나와요.",
    uninstall: `Get-CimInstance Win32_Process -Filter "Name like 'python%'" | ? { $_.CommandLine -like '*ReelsExtractor*' } | % { Stop-Process -Id $_.ProcessId -Force }; Get-ChildItem "$env:USERPROFILE\\ReelsExtractor" -Exclude data -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force; Remove-Item "$([Environment]::GetFolderPath('Startup'))\\ReelsExtractor.lnk", "$([Environment]::GetFolderPath('Startup'))\\ReelsExtractor.vbs", "$([Environment]::GetFolderPath('Desktop'))\\릴스 A+B=C.lnk", "$([Environment]::GetFolderPath('Programs'))\\릴스 A+B=C.lnk", "HKCU:\\Software\\Classes\\reelsabc" -Recurse -Force -ErrorAction SilentlyContinue`,
  },
};
function renderSetup() {
  const o = SETUP[setupOS];
  $$(".os-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.os === setupOS));
  $("#installCmd").textContent = o.cmd;
  $("#stepOpen").innerHTML = o.open;
  $("#stepPaste").innerHTML = o.paste;
  $("#uninstallHelp").textContent = o.uninstallHelp;
  $("#uninstallCmd").textContent = o.uninstall;
  const st = $("#setupStatus");
  st.className = "setup-status" + (helper.ok ? " ok" : "");
  st.innerHTML = !IS_LOCAL
    ? "설치가 끝나면 <b>릴스 A+B=C</b> 프로그램이 자동으로 열려요"
    : helper.ok
    ? "✅ 추출기가 켜져 있어요. <b>만들기</b> 탭에서 바로 쓰면 돼요."
    : "⏳ 추출기가 꺼져 있어요. 위 설치 명령을 다시 실행해 주세요.";
}
$$(".os-tabs button").forEach((b) => b.addEventListener("click", () => { setupOS = b.dataset.os; renderSetup(); }));
const copyText = (t, btn) => navigator.clipboard.writeText(t).then(() => {
  const old = btn.textContent;
  btn.textContent = "복사됨 ✓";
  setTimeout(() => (btn.textContent = old), 1600);
});
$("#copyCmd").addEventListener("click", (e) => copyText(SETUP[setupOS].cmd, e.currentTarget));
$("#copyUninstall").addEventListener("click", (e) => copyText(SETUP[setupOS].uninstall, e.currentTarget));
function goLocal() {
  let hash = "";
  if (state.refs.length || state.saved.length) {
    const payload = encodeURIComponent(JSON.stringify({ groups: state.groups, refs: state.refs, saved: state.saved }));
    if (payload.length < 1_500_000) hash = `#import=${payload}`;
  }
  location.href = `${LOCAL_URL}/${hash}`;
}

document.addEventListener("click", async (e) => {
  if (e.target.closest(".open-app")) { e.preventDefault(); openApp(false); return; }
  const link = e.target.closest("[data-tab-link]");
  if (link) {
    showTab(link.dataset.tabLink);
  }
});
$("#saveSettings").addEventListener("click", () => {
  state.settings = { helper: $("#setHelper").value.trim(), model: $("#setModel").value, modelChosen: true, language: $("#setLang").value, cookies: $("#setCookies").value };
  save();
  toast("저장했어요");
  checkHelper();
});
$("#exportBtn").addEventListener("click", async () => {
  if (IS_LOCAL) {
    await pushState();
    try { const r = await api("/api/export", {}); toast(`다운로드 폴더에 저장했어요: ${r.path.split(/[\\/]/).pop()}`, 3500); return; } catch {}
  }
  const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `reels-abc-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
});
$("#importFile").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  try {
    const data = JSON.parse(await f.text());
    if (!Array.isArray(data.refs)) throw new Error();
    const ids = new Set(state.refs.map((r) => r.id));
    for (const r of data.refs) {
      if (ids.has(r.id)) continue;
      r.units.forEach((u) => (u.id ||= uid()));
      if (!r.sectioned) { autoSections(r.units); r.sectioned = true; }
      state.refs.push(r);
    }
    const sids = new Set(state.saved.map((r) => r.id));
    state.saved.push(...(data.saved || []).filter((r) => !sids.has(r.id)));
    save(); renderBoard();
    toast("가져왔어요 (기존 것과 합쳤어요)");
  } catch { toast("올바른 백업 파일이 아니에요"); }
  e.target.value = "";
});

// ------------------------------------------------------------ 탭
function showTab(name) {
  $$(".tabs button").forEach((x) => x.classList.toggle("active", x.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + name));
  if (name === "work") renderBoard();
  if (name === "saved") renderSaved();
  if (name === "settings") renderSettings();
}
$$(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

function importFromHash() {
  if (!location.hash.startsWith("#import=")) return;
  try {
    const data = JSON.parse(decodeURIComponent(location.hash.slice(8)));
    const ids = new Set(state.refs.map((r) => r.id));
    const fresh = (data.refs || []).filter((r) => !ids.has(r.id));
    state.refs.push(...fresh);
    const sids = new Set(state.saved.map((r) => r.id));
    state.saved.push(...(data.saved || []).filter((r) => !sids.has(r.id)));
    state.groups = [...new Set([...state.groups, ...(data.groups || []), ...state.refs.map((r) => r.group)])].sort();
    if (fresh.length) setTimeout(() => toast(`레퍼런스 ${fresh.length}개를 옮겨왔어요`), 300);
  } catch {}
  history.replaceState(null, "", location.pathname);
}

let isRemote = false;
if (!IS_LOCAL) {
  isRemote = true;
  document.body.classList.add("remote");
  // 예전 버전의 "설치했으면 내 컴퓨터 주소로 자동 이동" 표시는 지움 (지운 뒤 없는 곳으로 이동하던 문제)
  try { localStorage.removeItem("reels-abc:installed"); } catch {}
  // 설치된 프로그램이 있으면 자동으로 프로그램을 엶 (reelsabc:// 링크).
  // 프로그램이 없으면(지웠거나 예전 버전) 아무 일도 일어나지 않고 이 설치 안내 페이지에 그대로 남음.
  const params = new URLSearchParams(location.search);
  if (!params.has("stay")) setTimeout(() => openApp(true), 400);
}
function openApp(auto) {
  const st = $("#openStatus");
  st.classList.remove("hidden");
  let left = false;
  const onBlur = () => { left = true; };
  window.addEventListener("blur", onBlur, { once: true });
  try { location.href = "reelsabc://open"; } catch {}
  setTimeout(() => {
    window.removeEventListener("blur", onBlur);
    st.classList.toggle("ok", left);
    st.innerHTML = left
      ? "✅ 프로그램을 열었어요. 이 창은 닫아도 돼요."
      : auto ? "" : "프로그램이 열리지 않았어요. 아래에서 설치해 주세요.";
    if (!left && auto) st.classList.add("hidden");
  }, 2500);
}

importFromHash();
renderBoard();
recombine();
renderSettings();
if (isRemote) showTab("settings");
else checkHelper();

if (IS_LOCAL) (async () => {
  let fileState = null;
  try { fileState = await (await fetch(`${location.origin}/api/state`)).json(); } catch {}
  if (fileState === null) return; // 예전 추출기: 브라우저 저장만 사용
  serverReady = true;
  if (hasData(fileState)) {
    const local = state;
    state = normalize(fileState);
    // 이 브라우저에만 있던 레퍼런스가 있으면 합침 (예전 버전에서 쓰던 데이터)
    const ids = new Set(state.refs.map((r) => r.id));
    const extra = local.refs.filter((r) => !ids.has(r.id));
    if (extra.length) { state.refs.push(...extra); state.groups = [...new Set([...state.groups, ...extra.map((r) => r.group)])].sort(); }
    const sids = new Set(state.saved.map((r) => r.id));
    const extraSaved = local.saved.filter((r) => !sids.has(r.id));
    state.saved.push(...extraSaved);
    if (extra.length || extraSaved.length) pushState();
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch {}
    cDirty = false;
    renderCols(); recombine();
  } else if (hasData(state)) {
    pushState(); // 처음: 브라우저에 있던 데이터를 컴퓨터 파일로 옮김
  }
})();
// 설치 직후 바로 초록불이 켜지도록: 꺼져 있을 땐 3초마다, 켜져 있으면 20초마다 확인
if (!isRemote) setTimeout(backfillStats, 1500);
if (!isRemote) (function poll() { setTimeout(() => checkHelper().finally(poll), helper.ok ? 20000 : 10000); })();

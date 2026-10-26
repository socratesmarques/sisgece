'use strict';
/* =======================================================================
   SISGECE — front-end
   1) CONFIG + API   → único ponto de contato com o backend
   2) MOCK           → banco de demonstração (localStorage). Apague ao integrar.
   3) INTERFACE      → telas, formulários, painéis (não precisa mexer)

   PARA INTEGRAR: CONFIG.USE_MOCK = false e implemente as rotas abaixo.
   - Sessão: cookie httpOnly (o front envia credentials:'include').
   - Erros: status != 2xx com { "message": "texto" } (o texto é exibido).
   - O SERVIDOR deve validar tudo (perfil, campos, etapas, CPF) e gravar auditoria.
     As travas do front são só de usabilidade.
   Perfis (role): superuser | management | reception | gate
   ======================================================================= */
const CONFIG = { USE_MOCK: true, API_BASE: '/api' };

const ENDPOINTS = {
  me:                 ['GET',    '/auth/me'],                 // -> usuário logado ou null
  login:              ['POST',   '/auth/login'],              // {identity,password,area:'management'|'gate'} -> usuário
  logout:             ['POST',   '/auth/logout'],
  stats:              ['GET',    '/estatisticas'],            // público -> {total,pending,approved,done}
  criarSolicitacao:   ['POST',   '/solicitacoes'],            // público -> {protocol}
  listarSolicitacoes: ['GET',    '/solicitacoes'],            // gestão: todas | recepção/portaria: approved+done
  decidir:            ['PATCH',  '/solicitacoes/:id/decisao'],// {id,approve:boolean,reason}
  confirmarEtapa:     ['PATCH',  '/solicitacoes/:id/etapa'],  // {id,step:'reception'|'gate'} (servidor grava usuário e horário)
  listarUsuarios:     ['GET',    '/usuarios'],                // só superuser
  criarUsuario:       ['POST',   '/usuarios'],                // {name,identity,password,role}
  editarUsuario:      ['PUT',    '/usuarios/:id'],            // {id,name,identity,password?,role}
  desativarUsuario:   ['DELETE', '/usuarios/:id']
};
/* Formato de uma solicitação:
   {id,protocol,type:'aluno'|'responsavel',requesterName,studentName,enrollment,course,guardianName,
    guardianPhone,cpf,kinship,exitType,date:'AAAA-MM-DD',time:'HH:MM',justification,createdAt,
    status:'pending'|'approved'|'rejected'|'done', decision:{by,at,reason}|null,
    reception:{checked,at,by}, gate:{checked,at,by}} */

async function call(name, p = {}) {
  if (CONFIG.USE_MOCK) return Mock[name](p);
  const [method, path] = ENDPOINTS[name];
  const r = await fetch(CONFIG.API_BASE + path.replace(':id', encodeURIComponent(p.id ?? '')), {
    method, credentials: 'include', headers: { 'Content-Type': 'application/json' },
    body: method === 'GET' || method === 'DELETE' ? undefined : JSON.stringify(p)
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).message || 'Erro ' + r.status);
  return r.status === 204 ? null : r.json();
}

/* ======================= 2) MOCK (demonstração) ======================= */
const Mock = (() => {
  const KEY = 'sisgece_demo_v1', SES = 'sisgece_session_v1', wait = () => new Promise(r => setTimeout(r, 80));
  const seed = () => ({ requests: [], audit: [], users: [
    { id: 'root', name: 'Professor Ademir', identity: 'root', password: 'toor', role: 'superuser', active: true },
    { id: 'sudo', name: 'Porteiro (Portaria)', identity: 'sudo', password: 'odus', role: 'gate', active: true },
    { id: 'recepcao', name: 'Equipe da Recepção', identity: 'recepcao', password: 'Recepcao@123', role: 'reception', active: true }] });
  let db = null;
  try { db = JSON.parse(localStorage.getItem(KEY)); } catch {}
  if (!db?.users || !db?.requests) db = seed();
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(db)); } catch {} };
  const key = v => { v = String(v || '').trim().toLowerCase(); return /^[\d.\-\/\s]+$/.test(v) ? v.replace(/\D/g, '') : v; };
  const cur = () => db.users.find(u => u.id === sessionStorage.getItem(SES) && u.active) || null;
  const need = (...roles) => { const u = cur(); if (!u || !roles.includes(u.role)) throw new Error('Acesso negado.'); return u; };
  const pub = u => ({ id: u.id, name: u.name, identity: u.identity, role: u.role, active: u.active });
  const log = (action, rid, detail = '') => { db.audit.unshift({ action, rid, detail, by: cur()?.name || 'Visitante', at: new Date().toISOString() }); db.audit.length = Math.min(db.audit.length, 500); };
  const find = id => db.requests.find(r => r.id === id) || (() => { throw new Error('Solicitação não encontrada.'); })();
  const uid = () => crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random());
  const AREA = { management: ['superuser', 'management'], gate: ['superuser', 'reception', 'gate'] };
  return {
    async me() { return cur() ? pub(cur()) : null; },
    async login({ identity, password, area }) { await wait();
      const u = db.users.find(x => x.active && key(x.identity) === key(identity) && x.password === password);
      if (!u || !AREA[area].includes(u.role)) throw new Error('Identificação, senha ou permissão inválida.');
      sessionStorage.setItem(SES, u.id); return pub(u); },
    async logout() { sessionStorage.removeItem(SES); },
    async stats() { const c = s => db.requests.filter(r => r.status === s).length;
      return { total: db.requests.length, pending: c('pending'), approved: c('approved'), done: c('done') }; },
    async criarSolicitacao(d) { await wait();
      const req = { ...d, id: uid(), protocol: 'SG-' + new Date().getFullYear() + '-' + Math.random().toString(36).slice(2, 8).toUpperCase(),
        createdAt: new Date().toISOString(), status: 'pending', decision: null, reception: { checked: false, at: null, by: null }, gate: { checked: false, at: null, by: null } };
      db.requests.unshift(req); log('Solicitação criada', req.id, req.protocol); save(); return { protocol: req.protocol }; },
    async listarSolicitacoes() { const u = need('superuser', 'management', 'reception', 'gate');
      const l = ['reception', 'gate'].includes(u.role) ? db.requests.filter(r => ['approved', 'done'].includes(r.status)) : db.requests;
      return structuredClone(l); },
    async decidir({ id, approve, reason }) { await wait(); const u = need('superuser', 'management'), r = find(id);
      if (r.status !== 'pending') throw new Error('Esta solicitação já foi analisada.');
      if (!approve && String(reason || '').trim().length < 4) throw new Error('Informe o motivo do indeferimento.');
      r.status = approve ? 'approved' : 'rejected'; r.decision = { by: u.name, at: new Date().toISOString(), reason: approve ? '' : reason.trim() };
      log(approve ? 'Solicitação autorizada' : 'Solicitação indeferida', id, r.protocol); save(); },
    async confirmarEtapa({ id, step }) { await wait(); const r = find(id);
      if (!['approved', 'done'].includes(r.status)) throw new Error('A solicitação não está autorizada.');
      if (step === 'reception') { const u = need('superuser', 'reception'); if (r.reception.checked) throw new Error('Etapa já confirmada.');
        r.reception = { checked: true, at: new Date().toISOString(), by: u.name }; log('Recepção confirmou apresentação', id, r.protocol); }
      else { const u = need('superuser', 'gate'); if (!r.reception.checked) throw new Error('A recepção deve confirmar primeiro.'); if (r.gate.checked) throw new Error('Etapa já confirmada.');
        r.gate = { checked: true, at: new Date().toISOString(), by: u.name }; r.status = 'done'; log('Portaria confirmou saída concluída', id, r.protocol); }
      save(); },
    async listarUsuarios() { need('superuser'); return db.users.map(pub); },
    async criarUsuario(d) { await wait(); need('superuser');
      if (db.users.some(x => key(x.identity) === key(d.identity))) throw new Error('Já existe um usuário com essa identificação.');
      db.users.push({ id: uid(), name: d.name, identity: d.identity, password: d.password, role: d.role, active: true }); log('Usuário criado', '', d.name); save(); },
    async editarUsuario(d) { await wait(); need('superuser'); const u = db.users.find(x => x.id === d.id); if (!u) throw new Error('Usuário não encontrado.');
      if (db.users.some(x => x.id !== d.id && key(x.identity) === key(d.identity))) throw new Error('Já existe um usuário com essa identificação.');
      Object.assign(u, { name: d.name, identity: d.identity, role: d.role }); if (d.password) u.password = d.password; log('Usuário editado', '', d.name); save(); },
    async desativarUsuario({ id }) { await wait(); need('superuser'); const u = db.users.find(x => x.id === id);
      if (!u || u.id === 'root') throw new Error('Este usuário não pode ser desativado.'); u.active = false; log('Usuário desativado', '', u.name); save(); }
  };
})();

/* ======================= 3) INTERFACE ======================= */
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
let me = null, reqs = [], users = [], st = { total: 0, pending: 0, approved: 0, done: 0 }, noticeTimer;

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const txt = v => String(v || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const dateBR = v => v ? new Date(v + 'T12:00:00').toLocaleDateString('pt-BR') : '—';
const dtBR = v => v ? new Date(v).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—';
const today = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
const roleLabel = r => ({ superuser: 'Superusuário', management: 'Gestão / Coordenação', reception: 'Recepção', gate: 'Portaria' })[r] || r;
const statusLabel = s => ({ pending: 'Aguardando análise', approved: 'Autorizada', rejected: 'Indeferida', done: 'Saída concluída' })[s] || s;
const isMgmt = () => !!me && ['superuser', 'management'].includes(me.role);
const isGateArea = () => !!me && ['superuser', 'reception', 'gate'].includes(me.role);
const canReception = () => ['superuser', 'reception'].includes(me?.role);
const canGate = r => ['superuser', 'gate'].includes(me?.role) && r.reception.checked;
const cpfOk = c => { c = c.replace(/\D/g, ''); if (c.length !== 11 || /^(\d)\1+$/.test(c)) return false;
  const d = n => { let s = 0; for (let i = 0; i < n; i++) s += c[i] * (n + 1 - i); return (s * 10 % 11) % 10; }; return d(9) == c[9] && d(10) == c[10]; };

function msg(t, type = 'success') { const n = $('#notice'); n.textContent = t; n.className = 'show ' + type; clearTimeout(noticeTimer); noticeTimer = setTimeout(() => n.className = '', 5000); }
async function safe(fn) { try { return await fn(); } catch (e) { msg(e.message || 'Erro inesperado.', 'error'); } }

/* ---------- Dados ---------- */
async function reload() {
  try { st = await call('stats'); } catch {}
  reqs = []; users = [];
  if (me) { try { reqs = await call('listarSolicitacoes'); } catch {} }
  if (me?.role === 'superuser') { try { users = await call('listarUsuarios'); } catch {} }
  renderAll();
}

/* ---------- Navegação e conta ---------- */
function go(id) {
  $$('.view').forEach(v => v.classList.toggle('active', v.id === id));
  $$('[data-view].nav-link').forEach(b => b.classList.toggle('active', b.dataset.view === id));
  $('#nav').classList.remove('open'); window.scrollTo({ top: 0, behavior: 'smooth' }); renderAll();
}
$$('[data-view]').forEach(b => b.addEventListener('click', () => go(b.dataset.view)));
$('#menuToggle').onclick = () => $('#nav').classList.toggle('open');
function headerAccount() {
  $('#account').innerHTML = me ? `<button id="accountBtn"><i class="bi bi-person-circle"></i> ${esc(me.name.split(' ')[0])}</button>` : `<button id="accountBtn"><i class="bi bi-box-arrow-in-right"></i> Entrar</button>`;
  $('#accountBtn').onclick = () => me ? logout() : go('management');
}
async function logout(ask = true) {
  if (ask && !confirm('Encerrar a sessão atual?')) return;
  await safe(() => call('logout')); me = null; headerAccount(); await reload(); msg('Sessão encerrada.');
}
$('#logoutManagement').onclick = () => logout(false);
$('#logoutGate').onclick = () => logout(false);
$$('.showpass').forEach(b => b.onclick = () => { const i = b.previousElementSibling; i.type = i.type === 'password' ? 'text' : 'password'; b.innerHTML = `<i class="bi bi-eye${i.type === 'password' ? '' : '-slash'}"></i>`; });

/* ---------- Início ---------- */
function renderStats() { $('#total').textContent = st.total; $('#pending').textContent = st.pending; $('#approved').textContent = st.approved; $('#done').textContent = st.done; }

/* ---------- Formulário de solicitação ---------- */
const NAMES = {
  aluno: ['studentName', 'enrollment', 'guardianName', 'guardianPhone', 'exitType'],
  responsavel: ['requesterName', 'cpf', 'phone', 'studentNameGuardian', 'kinship', 'exitTypeGuardian']
};
function setType(type) {
  const a = type === 'aluno';
  $('#studentFields').classList.toggle('hidden', !a); $('#guardianFields').classList.toggle('hidden', a);
  $$('.radio-card').forEach(l => l.classList.toggle('selected', l.querySelector('input').value === type));
  $('#studentFields').querySelectorAll('input,select').forEach(e => e.required = a && NAMES.aluno.includes(e.name));
  $('#guardianFields').querySelectorAll('input,select').forEach(e => e.required = !a && NAMES.responsavel.includes(e.name));
}
$$('input[name=type]').forEach(e => e.onchange = () => setType(e.value));
$('#exitDate').min = today(); $('#exitDate').value = today();
$('#justification').addEventListener('input', e => $('#count').textContent = e.target.value.length + ' / 800');
$('input[name=cpf]').addEventListener('input', e => e.target.value = e.target.value.replace(/\D/g, '').slice(0, 11).replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d{1,2})$/, '$1-$2'));
$('#requestForm').addEventListener('reset', () => setTimeout(() => { setType('aluno'); $('#count').textContent = '0 / 800'; $('#exitDate').value = today(); $$('.invalid').forEach(x => x.classList.remove('invalid')); }, 0));

$('#requestForm').onsubmit = async e => {
  e.preventDefault();
  const f = e.currentTarget, type = $('input[name=type]:checked').value, a = type === 'aluno';
  $$('.invalid').forEach(x => x.classList.remove('invalid'));
  let ok = true;
  for (const n of [...NAMES[type], 'date', 'time', 'justification']) { const el = f.elements[n]; if (!el?.value?.trim()) { el?.classList.add('invalid'); ok = false; } }
  if ($('#justification').value.trim().length < 8) { $('#justification').classList.add('invalid'); ok = false; }
  if (!a && f.elements.cpf.value && !cpfOk(f.elements.cpf.value)) { f.elements.cpf.classList.add('invalid'); msg('CPF inválido.', 'error'); return; }
  if ($('#exitDate').value < today()) { $('#exitDate').classList.add('invalid'); msg('A data prevista não pode estar no passado.', 'error'); return; }
  if (!$('#truth').checked) { msg('Confirme a veracidade das informações.', 'error'); ok = false; }
  if (!ok) { msg('Revise os campos obrigatórios destacados.', 'error'); return; }
  const d = Object.fromEntries(new FormData(f));
  const payload = { type, requesterName: a ? d.studentName : d.requesterName, studentName: a ? d.studentName : d.studentNameGuardian,
    enrollment: a ? d.enrollment : (d.enrollmentGuardian || ''), course: d.course || '', guardianName: a ? d.guardianName : d.requesterName,
    guardianPhone: a ? d.guardianPhone : d.phone, cpf: d.cpf || '', kinship: d.kinship || '', exitType: a ? d.exitType : d.exitTypeGuardian,
    date: d.date, time: d.time, justification: d.justification.trim() };
  const r = await safe(() => call('criarSolicitacao', payload)); if (!r) return;
  f.reset(); await reload(); msg('Solicitação enviada. Protocolo: ' + r.protocol);
  modal('Solicitação registrada', `<div class="success"><h3>Pedido enviado com sucesso!</h3><p>Sua solicitação está aguardando análise da gestão.</p><div class="detail"><small>PROTOCOLO</small><b>${esc(r.protocol)}</b></div><p class="modal-hint">Guarde o protocolo para acompanhar o pedido.</p></div>`, '<button class="btn btn-green" id="modalDone">Entendi</button>');
  $('#modalDone').onclick = closeModal;
};

/* ---------- Login ---------- */
function bindLogin(formId, kind) {
  $(formId).onsubmit = async e => {
    e.preventDefault(); const f = e.currentTarget, d = Object.fromEntries(new FormData(f)), err = $('#' + kind + 'Error');
    try { me = await call('login', { identity: d.identity.trim(), password: d.password, area: kind }); }
    catch (x) { err.textContent = x.message; return; }
    err.textContent = ''; f.reset(); headerAccount(); await reload(); msg('Bem-vindo(a), ' + me.name + '.');
  };
}
bindLogin('#loginManagement', 'management'); bindLogin('#loginGate', 'gate');

/* ---------- Gestão ---------- */
const mini = (l, n) => `<article><small>${l}</small><b>${n}</b></article>`;
const cnt = s => reqs.filter(r => r.status === s).length;
function renderManagement() {
  const ok = isMgmt(); $('#managementLogin').classList.toggle('hidden', ok); $('#managementDashboard').classList.toggle('hidden', !ok); if (!ok) return;
  $('#managementName').textContent = me.name; $('#managementRole').textContent = roleLabel(me.role);
  $('#managementStats').innerHTML = mini('Aguardando análise', cnt('pending')) + mini('Autorizadas', cnt('approved')) + mini('Indeferidas', cnt('rejected')) + mini('Saídas concluídas', cnt('done'));
  $('#adminPanel').classList.toggle('hidden', me.role !== 'superuser');
  renderManagementList(); if (me.role === 'superuser') renderUsers();
}
function renderManagementList() {
  const s = txt($('#managementSearch').value), f = $('#managementFilter').value;
  const l = reqs.filter(r => (f === 'all' || r.status === f) && (!s || txt([r.studentName, r.protocol, r.enrollment, r.requesterName].join(' ')).includes(s)));
  $('#managementList').innerHTML = l.length ? l.map(r => card(r, 'management')).join('') : empty();
}
function card(r, mode) {
  const actions = `<button class="btn btn-light" data-action="details" data-id="${esc(r.id)}"><i class="bi bi-eye"></i> Detalhes</button>` +
    (mode === 'management' && r.status === 'pending' ? `<button class="btn btn-green" data-action="approve" data-id="${esc(r.id)}">Autorizar</button><button class="btn soft-red" data-action="reject" data-id="${esc(r.id)}">Indeferir</button>` : '');
  const step = (key, title, help, who, canDo) => `<label class="gate-check ${r[key].checked ? 'done' : ''}"><input type="checkbox" data-check="${key}" data-id="${esc(r.id)}" ${r[key].checked ? 'checked' : ''} ${!canDo || r[key].checked ? 'disabled' : ''}><span><b>${title}</b><small>${help}</small>${r[key].checked ? `<small class="check-time">${esc(r[key].by)} · ${dtBR(r[key].at)}</small>` : ''}</span></label>`;
  const checks = mode === 'gate' ? `<div class="gate-checks">${step('reception', '1. Recepção', 'Confirma apresentação e registra o horário.', '', canReception())}${step('gate', '2. Portaria', 'Confirma que o aluno deixou o campus.', '', canGate(r))}</div>` : '';
  return `<article class="request-item"><div class="request-main"><div class="request-top"><b>${esc(r.studentName)}</b><span class="protocol">${esc(r.protocol)}</span><span class="badge-status ${r.status}">${statusLabel(r.status)}</span></div>
  <div class="request-details"><span><i class="bi bi-card-text"></i> ${esc(r.enrollment || 'Matrícula não informada')}</span><span><i class="bi bi-calendar3"></i> ${dateBR(r.date)} · ${esc(r.time)}</span><span><i class="bi bi-clock"></i> Enviada ${dtBR(r.createdAt)}</span></div>
  <p class="reason"><b>Justificativa:</b> ${esc(r.justification)}</p>${r.decision?.reason ? `<p class="reason"><b>Motivo do indeferimento:</b> ${esc(r.decision.reason)}</p>` : ''}${checks}</div><div class="request-actions">${actions}</div></article>`;
}
const empty = () => '<div class="empty"><i class="bi bi-inbox"></i><b>Nenhuma solicitação encontrada</b><br>Os pedidos aparecerão aqui quando forem enviados.</div>';
$('#managementSearch').oninput = renderManagementList; $('#managementFilter').onchange = renderManagementList;

/* ---------- Recepção / Portaria ---------- */
function renderGate() {
  const ok = isGateArea(); $('#gateLogin').classList.toggle('hidden', ok); $('#gateDashboard').classList.toggle('hidden', !ok); if (!ok) return;
  $('#gateName').textContent = me.name; $('#gateRole').textContent = roleLabel(me.role);
  $('#gateBanner').textContent = me.role === 'reception' ? 'Perfil Recepção: marque a primeira etapa após conferir o estudante.' : me.role === 'gate' ? 'Perfil Portaria: a segunda etapa só é liberada após a confirmação da recepção.' : 'Superusuário: pode testar as duas etapas de conferência.';
  renderGateList();
}
function renderGateList() {
  const s = txt($('#gateSearch').value), f = $('#gateFilter').value;
  const l = reqs.filter(r => ['approved', 'done'].includes(r.status)).filter(r => {
    if (f === 'active' && r.status === 'done') return false;
    if (f === 'reception' && r.reception.checked) return false;
    if (f === 'gate' && (!r.reception.checked || r.gate.checked)) return false;
    if (f === 'done' && r.status !== 'done') return false;
    return !s || txt([r.studentName, r.protocol, r.enrollment].join(' ')).includes(s);
  });
  $('#gateList').innerHTML = l.length ? l.map(r => card(r, 'gate')).join('') : empty();
}
$('#gateSearch').oninput = renderGateList; $('#gateFilter').onchange = renderGateList;

async function checkStep(id, step, checked) {
  const r = reqs.find(x => x.id === id); if (!r || !checked) return;
  if (step === 'reception' && !confirm('Confirmar apresentação de ' + r.studentName + ' na recepção? O horário atual será registrado.')) return renderGateList();
  if (step === 'gate' && !confirm('Confirmar que ' + r.studentName + ' efetivamente deixou o campus?')) return renderGateList();
  const ok = await safe(() => call('confirmarEtapa', { id, step }).then(() => true));
  await reload(); if (ok) msg(step === 'reception' ? 'Horário da recepção registrado.' : 'Saída concluída: as duas etapas foram registradas.');
}

/* ---------- Modal ---------- */
function modal(title, body, footer = '') {
  $('#modalTitle').textContent = title; $('#modalEyebrow').textContent = 'SISGECE'; $('#modalBody').innerHTML = body; $('#modalFooter').innerHTML = footer;
  $('#modalBackdrop').classList.remove('hidden'); document.body.style.overflow = 'hidden';
}
function closeModal() { $('#modalBackdrop').classList.add('hidden'); document.body.style.overflow = ''; }
$('#closeModal').onclick = closeModal;
$('#modalBackdrop').onclick = e => { if (e.target.id === 'modalBackdrop') closeModal(); };
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

function detailsHTML(r) {
  const f = [['Protocolo', r.protocol], ['Status', statusLabel(r.status)], ['Solicitante', r.requesterName], ['Tipo de solicitante', r.type === 'aluno' ? 'Aluno' : 'Responsável'], ['Aluno', r.studentName],
    ['Matrícula', r.enrollment || 'Não informada'], ['Curso / turma', r.course || 'Não informado'], ['Responsável', r.guardianName || '—'], ['Contato', r.guardianPhone || '—'], ['Parentesco', r.kinship || '—'],
    ['Tipo de saída', r.exitType], ['Data prevista', dateBR(r.date)], ['Horário previsto', r.time], ['Criada em', dtBR(r.createdAt)]];
  const dec = r.decision ? `Decisão por ${esc(r.decision.by)} · ${dtBR(r.decision.at)}${r.decision.reason ? '\nMotivo: ' + esc(r.decision.reason) : ''}` : 'Sem decisão registrada';
  return `<div class="detail-grid">${f.map(([k, v]) => `<div class="detail"><small>${esc(k)}</small><b>${esc(v)}</b></div>`).join('')}</div>
  <h4 class="modal-label">Justificativa</h4><div class="modal-copy">${esc(r.justification)}</div>
  <h4 class="modal-label">Decisão / conferências</h4><div class="modal-copy">${dec}\nRecepção: ${r.reception.checked ? esc(r.reception.by) + ' · ' + dtBR(r.reception.at) : 'Pendente'}\nPortaria: ${r.gate.checked ? esc(r.gate.by) + ' · ' + dtBR(r.gate.at) : 'Pendente'}</div>`;
}

async function decision(id, approve) {
  const r = reqs.find(x => x.id === id); if (!r || !isMgmt() || r.status !== 'pending') return;
  if (approve) {
    if (!confirm('Autorizar a saída de ' + r.studentName + '?')) return;
    if (await safe(() => call('decidir', { id, approve: true, reason: '' }).then(() => true))) { await reload(); msg('Solicitação autorizada.'); }
    return;
  }
  modal('Indeferir solicitação', `<p class="modal-copy">Informe o motivo do indeferimento de <b>${esc(r.studentName)}</b>.</p><label class="modal-label">Motivo do indeferimento *</label><textarea id="rejectReason" class="modal-input" rows="3" maxlength="300" placeholder="Explique o motivo..."></textarea>`,
    '<button class="btn btn-light" id="cancelReject">Cancelar</button><button class="btn btn-green" id="confirmReject">Confirmar indeferimento</button>');
  $('#cancelReject').onclick = closeModal;
  $('#confirmReject').onclick = async () => {
    const reason = $('#rejectReason').value.trim(); if (reason.length < 4) return msg('Informe o motivo do indeferimento.', 'error');
    if (await safe(() => call('decidir', { id, approve: false, reason }).then(() => true))) { closeModal(); await reload(); msg('Solicitação indeferida.'); }
  };
}

/* ---------- Usuários (superusuário) ---------- */
function renderUsers() {
  $('#usersList').innerHTML = users.map(u => `<div class="user-row"><span><b>${esc(u.name)} ${u.active ? '' : '(inativo)'}</b><small>${esc(u.identity)} · ${roleLabel(u.role)}</small></span><div class="user-actions">${u.id !== 'root' && u.active ? `<button data-user="${esc(u.id)}" data-op="edit" title="Editar"><i class="bi bi-pencil"></i></button><button class="del" data-user="${esc(u.id)}" data-op="delete" title="Desativar"><i class="bi bi-person-x"></i></button>` : (u.id === 'root' ? 'Superusuário protegido' : '')}</div></div>`).join('');
}
$('#addUser').onclick = () => editUser(null);
function editUser(u) {
  if (me?.role !== 'superuser') return msg('Apenas o superusuário pode administrar usuários.', 'error');
  const opt = (v, t) => `<option value="${v}" ${u?.role === v ? 'selected' : ''}>${t}</option>`;
  modal(u ? 'Editar usuário' : 'Adicionar usuário', `<label class="modal-label">Nome completo *</label><input id="userName" class="modal-input" value="${esc(u?.name || '')}">
  <label class="modal-label">Matrícula, CPF ou usuário *</label><input id="userIdentity" class="modal-input" value="${esc(u?.identity || '')}" autocomplete="off">
  <label class="modal-label">Senha ${u ? '(em branco para manter)' : '*'}</label><input id="userPassword" type="password" class="modal-input" autocomplete="new-password" minlength="8">
  <label class="modal-label">Perfil *</label><select id="userRole" class="modal-input">${opt('management', 'Gestão / Coordenação')}${opt('reception', 'Recepção')}${opt('gate', 'Portaria')}${opt('superuser', 'Superusuário')}</select>
  <p class="modal-hint">Demonstração local. No sistema real, o servidor deve guardar apenas o hash da senha.</p>`,
    '<button class="btn btn-light" id="cancelUser">Cancelar</button><button class="btn btn-green" id="saveUser">Salvar usuário</button>');
  $('#cancelUser').onclick = closeModal;
  $('#saveUser').onclick = async () => {
    const d = { name: $('#userName').value.trim(), identity: $('#userIdentity').value.trim(), password: $('#userPassword').value, role: $('#userRole').value };
    if (!d.name || !d.identity || (!u && !d.password) || (d.password && d.password.length < 8)) return msg('Preencha os campos e use senha com pelo menos 8 caracteres.', 'error');
    if (await safe(() => (u ? call('editarUsuario', { ...d, id: u.id }) : call('criarUsuario', d)).then(() => true))) { closeModal(); await reload(); msg('Usuário salvo.'); }
  };
}
async function deleteUser(u) {
  if (!u || u.id === 'root' || !confirm('Desativar o acesso de ' + u.name + '? O histórico será preservado.')) return;
  if (await safe(() => call('desativarUsuario', { id: u.id }).then(() => true))) { await reload(); msg('Usuário desativado.'); }
}

/* ---------- Eventos delegados ---------- */
document.addEventListener('click', e => {
  const b = e.target.closest('[data-action]');
  if (b) { const r = reqs.find(x => x.id === b.dataset.id);
    if (b.dataset.action === 'details' && r) { modal('Solicitação ' + r.protocol, detailsHTML(r), '<button class="btn btn-green" id="closeDetails">Fechar</button>'); $('#closeDetails').onclick = closeModal; }
    if (b.dataset.action === 'approve' && r) decision(r.id, true);
    if (b.dataset.action === 'reject' && r) decision(r.id, false); }
  const c = e.target.closest('[data-check]'); if (c) checkStep(c.dataset.id, c.dataset.check, c.checked);
  const ub = e.target.closest('[data-user]');
  if (ub) { const u = users.find(x => x.id === ub.dataset.user); if (ub.dataset.op === 'edit') editUser(u); if (ub.dataset.op === 'delete') deleteUser(u); }
});

function renderAll() { renderStats(); renderManagement(); renderGate(); }

/* ---------- Início ---------- */
(async () => {
  setType('aluno');
  if (CONFIG.USE_MOCK === false) $$('.demo-only').forEach(x => x.remove());
  try { me = await call('me'); } catch { me = null; }
  headerAccount(); await reload();
})();

const $ = (id) => document.getElementById(id);
const fields = (form) => Object.fromEntries(new FormData(form));
let user;
let pending = false;

async function run(work) {
  if (pending) return;
  pending = true;
  $("aviso").textContent = "Aguarde…";
  try {
    await work();
    if ($("aviso").textContent === "Aguarde…") $("aviso").textContent = "";
  } catch (e) {
    $("aviso").textContent = e.message;
    $("aviso").focus();
  } finally {
    pending = false;
  }
}
async function api(path, body) {
  const opts = body
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-SISGECE": "1" },
        body: JSON.stringify(body),
      }
    : {};
  const response = await fetch("/api/" + path, opts);
  const data = await response.json();
  if (!response.ok) throw Error(data.erro || "Falha na operação.");
  return data;
}
function bind(id, fn) {
  $(id).onsubmit = (e) => {
    e.preventDefault();
    run(() => fn(fields(e.target)));
  };
}
function node(parent, tag, text) {
  const el = document.createElement(tag);
  if (text != null) el.textContent = text;
  parent.append(el);
  return el;
}
function button(parent, label, fn) {
  const b = node(parent, "button", label);
  b.type = "button";
  b.onclick = () => run(fn);
  return b;
}
function pager(parent, page, more, load) {
  if (page > 1) button(parent, "Página anterior", () => load(page - 1));
  if (more) button(parent, "Próxima página", () => load(page + 1));
}
function formatDigits(digits, pattern) {
  let index = 0;
  let result = "";
  for (const character of pattern) {
    if (index === digits.length) break;
    result += character === "#" ? digits[index++] : character;
  }
  return result;
}
function formatCpf(value) {
  return formatDigits(value.replace(/\D/g, "").slice(0, 11), "###.###.###-##");
}
function formatPhone(value) {
  const digits = value.replace(/\D/g, "").slice(0, 15);
  const countryCode = value.trim().startsWith("+55") || (digits.startsWith("55") && digits.length > 11);
  if (countryCode) {
    return formatDigits(digits, digits.length > 12 ? "+## (##) #####-####" : "+## (##) ####-####");
  }
  if (value.trim().startsWith("+") || digits.length > 11) return "+" + digits;
  return formatDigits(digits, digits.length > 10 ? "(##) #####-####" : "(##) ####-####");
}
function maskInput(input, format, validate = () => {}) {
  function update() {
    const value = input.value;
    const caret = input.selectionStart;
    const digitsBefore = value.slice(0, caret).replace(/\D/g, "").length;
    input.value = format(value);
    if (document.activeElement === input && caret !== null) {
      let position = 0;
      let count = 0;
      if (caret === value.length) position = input.value.length;
      else {
        while (position < input.value.length && count < digitsBefore) {
          if (/\d/.test(input.value[position])) count++;
          position++;
        }
      }
      input.setSelectionRange(position, position);
    }
    validate(input.value);
  }
  input.addEventListener("beforeinput", (event) => {
    const backward = event.inputType === "deleteContentBackward";
    const forward = event.inputType === "deleteContentForward";
    if ((!backward && !forward) || input.selectionStart !== input.selectionEnd) return;
    let position = input.selectionStart;
    if (backward) {
      while (position > 0 && /\D/.test(input.value[position - 1])) position--;
      if (position > 0) input.setSelectionRange(position, position);
    } else {
      while (position < input.value.length && /\D/.test(input.value[position])) position++;
      if (position < input.value.length) input.setSelectionRange(position, position);
    }
  });
  input.addEventListener("input", update);
  input.addEventListener("change", update);
  update();
}
if ($("pedido")) {
  const form = $("pedido");
  form.origem.onchange = () => {
    $("familia").hidden = $("familia").disabled =
      form.origem.value !== "Responsável";
  };
  maskInput(form.cpf, formatCpf);
  maskInput(form.telefone, formatPhone, (value) => {
    const digits = value.replace(/\D/g, "");
    const valid = value.startsWith("+55")
      ? [12, 13].includes(digits.length)
      : value.startsWith("+") ? digits.length >= 10 && digits.length <= 15
        : [10, 11].includes(digits.length);
    form.telefone.setCustomValidity(
      !value || valid ? "" : "Informe o telefone completo com DDD.",
    );
  });
  form.addEventListener("reset", () => form.telefone.setCustomValidity(""));
  bind("pedido", async (body) => {
    await api("solicitar", body);
    $("recibo").textContent =
      "Solicitação enviada com sucesso! O pedido será analisado pela coordenação." +
      (form.dataset.whatsappAuto === "true"
        ? " Acompanhe as atualizações do processo pelo WhatsApp no número informado."
        : "");
    form.reset();
    form.origem.onchange();
    $("recibo").focus();
  });
} else {
  bind("login", async (body) => {
    await api("login", body);
    location.reload();
  });
  $("sair").onclick = () =>
    run(async () => {
      await api("logout", {});
      location.reload();
    });
  bind("filtro", () => list());
  const sections = {pedidos:"area-pedidos",historico:"historico-pedidos",equipe:"admin",mensagens:"mensagens-painel"};
  for (const [area,panel] of Object.entries(sections)) {
    $("ver-"+area).onclick = () => run(async () => {
      if ($("ver-mensagens").getAttribute("aria-pressed") === "true" &&
          area !== "mensagens" && messageIsDirty() &&
          !window.confirm("Descartar alterações não salvas da mensagem?")) return;
      for (const [key,id] of Object.entries(sections)) {
        $(id).hidden = key !== area;
        $("ver-"+key).setAttribute("aria-pressed", String(key === area));
      }
      if (area === "equipe") await accounts();
      if (area === "historico") await requestHistory();
      if (area === "mensagens") await loadMessageModels();
    });
  }
  bind("buscar-historico", () => requestHistory());
  $("mensagens-form").onsubmit = e => {e.preventDefault(); run(saveMessageModel);};
  $("mensagens-restaurar").onclick = () => {
    if (window.confirm("Restaurar o texto original e reativar este aviso?")) run(restoreMessageModel);
  };
  $("mensagens-texto").addEventListener("input", () => {updateMessageDirty(); scheduleMessagePreview();});
  $("mensagens-ativo").onchange = updateMessageDirty;
  $("mensagens-movimentacao").onchange = scheduleMessagePreview;
  $("mensagens-simular-avaliacao").onchange = scheduleMessagePreview;
  for (const control of document.querySelectorAll("[data-message-token]")) {
    control.onclick = () => insertMessageToken(control.dataset.messageToken);
  }
  $("adicionar").onclick = () => editAccount();
  $("cancelar").onclick = () => $("editor").close();
  $("conta").elements.perfil.onchange = roleHelp;
  bind("buscar-equipe", () => accounts());
  bind("filtro-contas", () => audit());
  document.querySelector(".audit-box").ontoggle = (e) => {
    if (e.target.open) run(() => audit());
  };
  bind("conta", async (body) => {
    const editing = Boolean(body.id);
    body.ativo = $("conta").elements.ativo.checked;
    if (editing) body.id = Number(body.id);
    else delete body.id;
    try {
      await api("contas", body);
    } catch (error) {
      $("erro-conta").textContent = error.message;
      return;
    }
    $("editor").close();
    if (body.id === user.id) { location.reload(); return; }
    await accounts();
    if (document.querySelector(".audit-box").open) await audit();
    $("aviso").textContent = editing ? "Alterações salvas." : "Funcionário adicionado.";
  });
  run(async () => {
    const response = await fetch("/api/me");
    const profile = await response.json();
    if (response.status === 401) return;
    if (!response.ok) throw Error("Não foi possível carregar o painel.");
    user = profile;
    $("entrada").hidden = true;
    $("painel").hidden = false;
    $("perfil").textContent = "Painel de " + user.perfil + " · " + user.nome;
    await list();
    $("areas").hidden = false;
    $("ver-equipe").hidden = user.perfil !== "superusuário";
    $("ver-mensagens").hidden = user.perfil !== "superusuário";
    if (user.perfil === "coordenação" || user.perfil === "superusuário") {
      $("avaliacoes-painel").hidden = false;
      $("atualizar-avaliacoes").onclick = () => run(loadRatings);
      await loadRatings();
    }
  });
}
async function list(page = 1) {
  const p = new URLSearchParams(fields($("filtro")));
  p.set("pagina", page);
  const el = $("lista");
  el.replaceChildren();
  const r = await api("pedidos?" + p);
  if (!r.itens.length) node(el, "p", "Nenhuma solicitação encontrada.");
  for (const item of r.itens) {
    const line = node(el, "article");
    line.className = "record";
    const name = node(line, "div");
    node(name, "strong", item.aluno);
    node(name, "small", item.tipo + " · " + item.protocolo);
    const status = node(
      line,
      "span",
      item.status === "APROVADA"
        ? [item.status, item.etapa].filter(Boolean).join(" · ")
        : item.status,
    );
    status.className = "badge";
    status.dataset.status = item.status;
    button(line, "Abrir detalhes", () => detail(item.id));
  }
  pager(el, page, r.mais, list);
}
async function detail(id, page = 1) {
  const el = $("detalhe");
  el.hidden = true;
  el.replaceChildren();
  const r = await api("pedidos/" + id + "?pagina=" + page);
  el.hidden = false;
  node(el, "h2", "Solicitação " + r.protocolo);
  const labels = {
    aluno: "Estudante",
    matricula: "Matrícula",
    responsavel: "Responsável",
    cpf: "CPF",
    parentesco: "Parentesco",
    telefone: "Telefone",
    origem: "Solicitante",
  };
  const facts = node(el, "dl");
  facts.className = "facts";
  for (const [k, v] of Object.entries({
    ...r.declarado,
    tipo: r.tipo,
    data: r.data_solicitada,
    horário: r.horario_solicitado,
    justificativa: r.justificativa,
    situação: r.status,
    etapa: r.etapa,
    mensagem: r.mensagem,
  })) {
    if (v) {
      const field = node(facts, "div");
      node(field, "dt", labels[k] || k[0].toUpperCase() + k.slice(1));
      node(field, "dd", k === "telefone" ? formatPhone(v) : v);
    }
  }
  if (r.status === "APROVADA" &&
      ["entrada", "saida", "saída"].includes(r.tipo.toLowerCase())) {
    const entryMovement = r.tipo.toLowerCase() === "entrada";
    node(el, "h3", entryMovement ? "Conferência da entrada" : "Conferência da saída");
    for (const [step, entry] of Object.entries(r.confirmacoes)) {
      const title =
        step === "recepção"
          ? entryMovement ? "Recepção · registro de entrada" : "Recepção · conferência"
          : "Portaria · saída efetiva";
      const check = node(el, "div");
      check.className = "check";
      node(check, "b", title);
      node(
        check,
        "small",
        entry ? entry.nome + " · " + entry.quando : "Aguardando confirmação",
      );
    }
  }
  const send = async (acao, extra = {}) => {
    await api("pedidos/" + id, { acao, ...extra });
    await list();
    await detail(id);
    $("aviso").textContent = "Ação registrada.";
  };
  const isExit = ["saida", "saída"].includes(r.tipo.toLowerCase());
  if (
    ["coordenação", "superusuário"].includes(user.perfil) &&
    (isExit || r.tipo.toLowerCase() === "entrada")
  ) {
    const note = node(
      node(el, "label", "Observação interna ou justificativa da correção"),
      "textarea",
    );
    note.maxLength = 2000;
    note.name = "nota";
    if (["PENDENTE", "RECEBIDA"].includes(r.status)) {
      node(
        el,
        "p",
        "Confira manualmente a identidade, os dados declarados e a autorização do responsável antes de decidir.",
      );
      const msg = node(
        node(
          el,
          "label",
          "Mensagem ao solicitante (motivo obrigatório na reprovação)",
        ),
        "textarea",
      );
      msg.maxLength = 2000;
      msg.name = "mensagem";
      for (const a of ["aprovar", "reprovar"])
        button(el, a, () => send(a, { nota: note.value, mensagem: msg.value }));
    } else {
      node(
        el,
        "p",
        isExit
          ? "Reabrir a análise invalida as duas confirmações. Corrigir a recepção também invalida a portaria."
          : "Reabrir a análise invalida a confirmação da entrada na recepção e devolve o pedido para PENDENTE.",
      );
      const actions = ["reabrir análise"];
      if ((isExit && r.etapa !== "aguardando") ||
          (!isExit && r.etapa === "entrada concluída"))
        actions.push("corrigir recepção");
      if (isExit && r.etapa === "saída concluída") actions.push("corrigir portaria");
      for (const a of actions)
        button(el, a, () => send(a, { nota: note.value }));
    }
  }
  if (r.status === "APROVADA" && (
    (user.perfil === "recepção" &&
      (isExit ? r.etapa === "aguardando" :
        r.tipo.toLowerCase() === "entrada" && r.etapa === "aguardando recepção")) ||
    (isExit && user.perfil === "portaria" && r.etapa === "recepção confirmada")
  )) {
    const box = node(
      node(
        el,
        "label",
        user.perfil === "recepção"
          ? isExit ? "Conferi a autorização de saída na recepção " :
            "Confirmo que a entrada foi registrada na recepção "
          : "Confirmo que o aluno deixou o campus ",
      ),
      "input",
    );
    box.type = "checkbox";
    const save = button(el, "Registrar confirmação", () => send(user.perfil));
    save.disabled = true;
    box.onchange = () => (save.disabled = !box.checked);
  }
  if (["coordenação", "superusuário"].includes(user.perfil)) {
    const section = node(el, "details");
    node(section, "summary", "Notificações pelo WhatsApp");
    const content = node(section, "div");
    section.ontoggle = async () => {
      if (!section.open) return;
      content.replaceChildren();
      try {
        const records = await api("pedidos/" + id + "/notificacoes");
        if (!records.itens.length) node(content, "p", "Nenhum envio registrado.");
        for (const record of records.itens) {
          node(content, "p", record.template_tipo + " · " + record.estado +
            " · tentativas: " + record.tentativas + (record.resultado ? " · " + record.resultado : ""));
        }
      } catch (_) { node(content, "p", "Não foi possível consultar os envios."); }
    };
  }
  node(el, "h3", "Histórico · horário de Fortaleza");
  for (const e of r.historico.itens)
    node(
      el,
      "article",
      [e.quando, e.acao, e.autor, e.nota].filter(Boolean).join(" · "),
    );
  pager(el, page, r.historico.mais, (p) => detail(id, p));
  el.scrollIntoView();
}
function roleHelp() {
  const descriptions = {
    "coordenação": "Analisa solicitações e decide sobre entradas e saídas.",
    "recepção": "Confere saídas aprovadas e registra a conclusão das entradas aprovadas.",
    "portaria": "Registra a saída após a conferência da recepção.",
    "superusuário": "Gerencia funcionários, permissões e análises."
  };
  $("ajuda-perfil").textContent = descriptions[$("conta").elements.perfil.value];
}
function editAccount(account) {
  const f = $("conta");
  f.reset();
  f.elements.id.value = account?.id || "";
  if (account) {
    for (const key of ["nome","usuario","perfil"]) f.elements[key].value = account[key];
  }
  f.elements.ativo.checked = account ? account.ativo : true;
  $("estado-conta").hidden = !account;
  f.elements.senha.required = !account;
  $("titulo-conta").textContent = account ? "Editar funcionário" : "Adicionar funcionário";
  $("rotulo-senha").textContent = account ? "Nova senha (opcional)" : "Senha de acesso";
  $("ajuda-senha").textContent = account ? "Deixe em branco para manter a senha atual." : "Use pelo menos 8 caracteres.";
  $("salvar").textContent = account ? "Salvar alterações" : "Criar conta";
  $("erro-conta").textContent = "";
  roleHelp();
  $("editor").showModal();
  f.elements.nome.focus();
}
async function accounts(page = 1) {
  const params = new URLSearchParams(fields($("buscar-equipe")));
  params.set("pagina",page);
  const r = await api("contas?"+params), el = $("contas");
  el.replaceChildren();
  if (!r.itens.length) node(el,"p","Nenhum funcionário encontrado.");
  for (const a of r.itens) {
    const line = node(el,"article");
    line.className = "person";
    const identity = node(line,"div");
    node(identity,"strong",a.nome);
    node(identity,"small",a.usuario);
    node(line,"span",a.perfil).className="role-name";
    node(line,"span",a.ativo ? "Ativo" : "Inativo").className="access-state "+(a.ativo?"enabled":"");
    button(line,"Editar",()=>editAccount(a)).setAttribute("aria-label","Editar "+a.nome);
  }
  pager(el,page,r.mais,accounts);
}
async function audit(page = 1) {
  const r = await api(
      "auditoria?pagina=" +
        page +
        "&" +
        new URLSearchParams(fields($("filtro-contas"))),
    ),
    el = $("audit");
  el.replaceChildren();
  if (!r.itens.length) node(el, "p", "Nenhum evento encontrado.");
  for (const e of r.itens)
    node(
      el,
      "article",
      [e.quando, e.nome, e.acao, e.nota].filter(Boolean).join(" · "),
    );
  pager(el, page, r.mais, audit);
}

async function requestHistory(page = 1) {
  const params = new URLSearchParams(fields($("buscar-historico")));
  params.set("pagina",page);
  const r = await api("historico?"+params), el = $("eventos-pedidos");
  el.replaceChildren();
  if (!r.itens.length) node(el,"p","Nenhum registro encontrado.");
  for (const e of r.itens) {
    const line = node(el,"article");
    node(line,"strong",e.aluno+" · "+e.tipo);
    node(line,"p",e.acao+(e.autor?" · "+e.autor:""));
    node(line,"small",e.quando+" · "+e.protocolo);
  }
  pager(el,page,r.mais,requestHistory);
}

async function loadRatings() {
  const target = $("avaliacoes-resumo");
  if (!target) return;
  target.replaceChildren();
  try {
    const stats = await api("notificacoes/avaliacoes/estatisticas");
    node(target, "p", stats.quantidade
      ? "Total de avaliações: " + stats.quantidade + " · Média: " + stats.media + " de 5"
      : "Ainda não há avaliações registradas.");
    if (stats.quantidade) {
      const scores = Object.entries(stats.distribuicao)
        .map(([score, count]) => score + " estrela(s): " + count)
        .join(" · ");
      node(target, "small", scores);
    }
  } catch (_) {
    node(target, "p", "Não foi possível carregar as avaliações.");
  }
}

let messageModels = [];
let selectedMessage = null;
let messagePreviewTimer = null;
let messagePreviewVersion = 0;

function insertMessageToken(token) {
  const input = $("mensagens-texto");
  const marker = "{" + token + "}";
  const start = input.selectionStart, end = input.selectionEnd;
  if (input.value.length - (end - start) + marker.length > input.maxLength) return;
  input.setRangeText(marker, start, end, "end");
  input.focus();
  updateMessageDirty();
  scheduleMessagePreview();
}
function updateMessageTokens() {
  const kind = selectedMessage;
  const allowed = new Set(["tipo", "data", "horario"]);
  if (kind === "aprovar") allowed.add("detalhes_solicitacao");
  if (kind === "recepção") allowed.add("detalhes_etapa");
  if (["reprovar", "recepção", "portaria"].includes(kind)) allowed.add("convite_avaliacao");
  for (const control of document.querySelectorAll("[data-message-token]")) {
    control.hidden = !allowed.has(control.dataset.messageToken);
  }
  $("mensagens-simular-avaliacao").checked = false;
  $("mensagens-simular-avaliacao").closest("label").hidden =
    !allowed.has("convite_avaliacao");
}

function selectedMessageModel() {
  return messageModels.find(item => item.tipo === selectedMessage);
}
function messageIsDirty() {
  const item = selectedMessageModel();
  return Boolean(item && ($("mensagens-texto").value.trim() !== item.texto ||
    $("mensagens-ativo").checked !== item.ativo));
}
function updateMessageDirty() {
  if (!selectedMessageModel()) return;
  const enabled = $("mensagens-ativo").checked;
  $("mensagens-contador").textContent = $("mensagens-texto").value.length + " / 1500";
  $("mensagens-salvar").disabled = !messageIsDirty();
  $("mensagens-feedback").textContent = messageIsDirty() ? "Alterações ainda não salvas." : "";
  $("mensagens-situacao").textContent = enabled ? "Ativa" : "Desativada";
  $("mensagens-situacao").classList.toggle("message-pill-off", !enabled);
}
function drawMessageList() {
  const target = $("mensagens-lista");
  target.replaceChildren();
  for (const item of messageModels) {
    const entry = node(target, "button");
    entry.type = "button";
    entry.className = "message-event";
    entry.setAttribute("aria-pressed", String(item.tipo === selectedMessage));
    const main = node(entry, "span");
    node(main, "strong", item.titulo);
    node(main, "small", item.personalizado ? "Personalizada" : "Texto padrão");
    node(entry, "span", item.ativo ? "Ativa" : "Pausada").className =
      "message-event-state" + (item.ativo ? "" : " message-event-off");
    entry.onclick = () => {
      if (item.tipo === selectedMessage) return;
      if (messageIsDirty() && !window.confirm("Descartar alterações não salvas da mensagem?")) return;
      run(() => selectMessageModel(item.tipo));
    };
  }
}
async function selectMessageModel(type) {
  const item = messageModels.find(entry => entry.tipo === type);
  if (!item) return;
  selectedMessage = type;
  $("mensagens-titulo").textContent = item.titulo;
  updateMessageTokens();
  $("mensagens-texto").value = item.texto;
  $("mensagens-ativo").checked = item.ativo;
  $("mensagens-restaurar").disabled = !item.personalizado && item.ativo;
  $("mensagens-subtitulo").textContent =
    "Edite a mensagem inteira. As alterações valem para novos eventos; a fila mantém os textos anteriores.";
  drawMessageList();
  updateMessageDirty();
  scheduleMessagePreview();
  await loadMessageHistory(type);
}
async function loadMessageModels(type = selectedMessage) {
  const result = await api("notificacoes/modelos");
  messageModels = result.itens;
  await selectMessageModel(messageModels.some(i => i.tipo === type) ?
    type : messageModels[0]?.tipo);
}
function scheduleMessagePreview() {
  window.clearTimeout(messagePreviewTimer);
  const revision = ++messagePreviewVersion, type = selectedMessage;
  if (!type) return;
  $("mensagens-previsao-estado").textContent = "Atualizando prévia…";
  messagePreviewTimer = window.setTimeout(async () => {
    try {
      const response = await api("notificacoes/modelos/prever", {
        tipo: type, texto: $("mensagens-texto").value,
        movimentacao: $("mensagens-movimentacao").value,
        simular_avaliacao: $("mensagens-simular-avaliacao").checked,
      });
      if (revision !== messagePreviewVersion) return;
      $("mensagens-previsao").textContent = response.texto;
      $("mensagens-previsao-estado").textContent = "Prévia ilustrativa · não enviada";
    } catch (error) {
      if (revision !== messagePreviewVersion) return;
      $("mensagens-previsao").textContent = "Corrija o conteúdo para visualizar a mensagem.";
      $("mensagens-previsao-estado").textContent = error.message;
    }
  }, 300);
}
async function saveMessageModel() {
  const item = selectedMessageModel();
  if (!item || !messageIsDirty()) return;
  try {
    await api("notificacoes/modelos", {
      tipo: item.tipo, texto: $("mensagens-texto").value,
      ativo: $("mensagens-ativo").checked, versao: item.versao, acao: "salvar",
    });
    await loadMessageModels(item.tipo);
    $("mensagens-feedback").textContent = "Mensagem salva. Novos eventos usarão esta configuração.";
  } catch (error) {
    $("mensagens-feedback").textContent = error.message;
    throw error;
  }
}
async function restoreMessageModel() {
  const item = selectedMessageModel();
  if (!item) return;
  try {
    await api("notificacoes/modelos", {tipo:item.tipo, versao:item.versao, acao:"restaurar"});
    await loadMessageModels(item.tipo);
    $("mensagens-feedback").textContent = "Texto padrão restaurado e aviso reativado.";
  } catch (error) {
    $("mensagens-feedback").textContent = error.message;
    throw error;
  }
}
async function loadMessageHistory(type) {
  const target = $("mensagens-historico");
  target.replaceChildren();
  try {
    const result = await api("notificacoes/modelos/historico?tipo=" + encodeURIComponent(type));
    if (selectedMessage !== type) return;
    if (!result.itens.length) {
      node(target, "p", "Este aviso ainda utiliza a configuração original.");
      return;
    }
    for (const item of result.itens) {
      const details = node(target, "details");
      details.className = "message-history-entry";
      const summary = node(details, "summary");
      node(summary, "strong", "Versão " + item.versao);
      node(summary, "span", (item.acao === "restaurar" ? "Restaurada" : "Alterada") +
        " · " + (item.ativo ? "Ativa" : "Pausada"));
      node(details, "small", item.autor + " · " +
        new Date(item.quando).toLocaleString("pt-BR", {dateStyle:"short",timeStyle:"short"}) +
        (item.completa ? " · Texto integral" : " · Texto do formato anterior"));
      node(details, "pre", item.texto);
    }
  } catch (_) {
    if (selectedMessage === type) node(target, "p", "Não foi possível carregar o histórico.");
  }
}

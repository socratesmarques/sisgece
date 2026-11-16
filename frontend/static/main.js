const $ = (id) => document.getElementById(id);
const fields = (form) => Object.fromEntries(new FormData(form));
let user;
let pending = false;
let selectedRequest;

async function run(work) {
  if (pending) return;
  pending = true;
  const buttons = [...document.querySelectorAll("button:not(:disabled)")];
  buttons.forEach((button) => (button.disabled = true));
  $("principal").setAttribute("aria-busy", "true");
  $("aviso").dataset.kind = "loading";
  $("aviso").textContent = "Aguarde…";
  try {
    await work();
    $("aviso").dataset.kind = "success";
    if ($("aviso").textContent === "Aguarde…") $("aviso").textContent = "";
  } catch (e) {
    $("aviso").dataset.kind = "error";
    $("aviso").textContent = e.message;
    $("aviso").focus();
  } finally {
    buttons.forEach((button) => { if (button.isConnected) button.disabled = false; });
    $("principal").setAttribute("aria-busy", "false");
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
  if (page === 1 && !more) return;
  const navigation = node(parent, "nav");
  navigation.className = "pager";
  navigation.setAttribute("aria-label", "Paginação");
  if (page > 1) button(navigation, "Página anterior", () => load(page - 1));
  if (more) button(navigation, "Próxima página", () => load(page + 1));
}
function statusBadge(parent, item) {
  const status = node(parent, "span", [item.status, item.status === "APROVADA" ? item.etapa : ""].filter(Boolean).join(" · "));
  status.className = "badge";
  status.dataset.status = item.status;
  return status;
}
function emptyState(parent, title, description) {
  const state = node(parent, "div");
  state.className = "empty-state";
  node(state, "strong", title);
  node(state, "p", description);
}
if ($("pedido")) {
  const form = $("pedido");
  function movementGuide() {
    const entry = form.elements.tipo.value === "Entrada";
    $("guia-entrada").hidden = !entry;
    $("guia-saida").hidden = entry;
    $("ajuda-movimento").textContent = entry
      ? "A coordenação analisará o pedido. A aprovação não registra a entrada física no campus."
      : "Aguarde a aprovação antes de seguir para a recepção.";
    $("nota-guia").textContent = entry
      ? "A aprovação do pedido não comprova a entrada física no campus. Siga as orientações da equipe."
      : "Guarde o código para consultar a situação e as mensagens da equipe.";
  }
  form.querySelectorAll("[name=tipo]").forEach(radio => radio.addEventListener("change", movementGuide));
  movementGuide();
  form.origem.onchange = () => {
    $("familia").hidden = $("familia").disabled =
      form.origem.value !== "Responsável";
  };
  form.telefone.oninput = () => {
    const v = form.telefone.value;
    form.telefone.setCustomValidity(
      /^[\d+() -]+$/.test(v) && /^\d{10,13}$/.test(v.replace(/\D/g, ""))
        ? ""
        : "Informe o telefone com DDD.",
    );
  };
  bind("pedido", async (body) => {
    const result = await api("solicitar", body);
    $("recibo").textContent =
      ("Solicitação salva. " + (body.tipo === "Entrada" ? "Seu pedido de entrada aguarda análise da coordenação." : "O envio ainda não autoriza a saída.")) + " Guarde seu código.\nCódigo de consulta: " +
      result.codigo;
    $("rastrear").elements.codigo.value = result.codigo;
    $("copiar").hidden = false;
    $("copiar").onclick = () =>
      run(async () => {
        await navigator.clipboard.writeText(result.codigo);
        $("aviso").textContent = "Código copiado.";
      });
    form.reset();
    movementGuide();
    form.origem.onchange();
    $("recibo").focus();
  });
  bind("rastrear", async (body) => {
    $("resultado").textContent = "";
    const r = await api("consulta", body);
    const result = $("resultado");
    node(result, "strong", "Solicitação de " + r.tipo.toLowerCase()).className = "result-title";
    statusBadge(result, r);
    const explanation = {
      PENDENTE: "Seu pedido está aguardando a análise da coordenação.",
      RECEBIDA: "Seu pedido foi recebido e aguarda análise da coordenação.",
      REPROVADA: "Seu pedido foi recusado. Confira o motivo informado pela coordenação.",
      APROVADA: r.tipo === "Entrada"
        ? "Pedido de entrada aprovado. Siga as orientações da equipe; esta aprovação não registra a entrada física."
        : r.etapa === "saída concluída" ? "A saída foi registrada pela portaria."
          : r.etapa === "recepção confirmada" ? "Conferência da recepção concluída. Siga para a portaria."
            : "Pedido aprovado. Apresente-se à recepção para a conferência.",
    };
    node(result, "span", explanation[r.status] || "Consulte as orientações da coordenação.").className = "result-description";
    if (r.mensagem) node(result, "span", "Mensagem da coordenação: " + r.mensagem).className = "result-message";
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
  bind("filtro", () => {
    selectedRequest = null;
    $("detalhe").hidden = true;
    return list();
  });
  $("limpar-filtros").onclick = () => run(async () => {
    $("filtro").reset();
    selectedRequest = null;
    $("detalhe").hidden = true;
    await list();
  });
  const sections = {pedidos:"area-pedidos",historico:"historico-pedidos",equipe:"admin"};
  for (const [area,panel] of Object.entries(sections)) {
    $("ver-"+area).onclick = () => run(async () => {
      for (const [key,id] of Object.entries(sections)) {
        $(id).hidden = key !== area;
        $("ver-"+key).setAttribute("aria-pressed", String(key === area));
      }
      if (area === "equipe") await accounts();
      if (area === "historico") await requestHistory();
    });
  }
  bind("buscar-historico", () => requestHistory());
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
  });
}
async function list(page = 1) {
  const p = new URLSearchParams(fields($("filtro")));
  p.set("pagina", page);
  const r = await api("pedidos?" + p);
  const el = $("lista");
  el.replaceChildren();
  $("resumo-lista").textContent = r.itens.length ? `${r.itens.length}${r.mais ? "+" : ""} nesta página` : "";
  if (!r.itens.length) emptyState(el, "Nenhuma solicitação encontrada", "Tente outro nome, matrícula ou período, ou limpe os filtros.");
  for (const item of r.itens) {
    const line = node(el, "article");
    line.className = "record";
    line.dataset.id = item.id;
    line.dataset.selected = String(item.id === selectedRequest);
    const name = node(line, "div");
    node(name, "strong", item.aluno);
    node(name, "small", item.tipo + " · " + item.protocolo);
    statusBadge(line, item);
    const open = button(line, "Abrir detalhes", () => detail(item.id));
    open.className = "secondary";
    open.setAttribute("aria-controls", "detalhe");
    open.setAttribute("aria-expanded", String(item.id === selectedRequest));
  }
  pager(el, page, r.mais, list);
}
async function detail(id, page = 1) {
  const r = await api("pedidos/" + id + "?pagina=" + page),
    el = $("detalhe");
  el.hidden = false;
  el.replaceChildren();
  selectedRequest = id;
  for (const record of $("lista").querySelectorAll(".record")) {
    const selected = Number(record.dataset.id) === id;
    record.dataset.selected = String(selected);
    record.querySelector("button").setAttribute("aria-expanded", String(selected));
  }
  const heading = node(el, "div");
  heading.className = "detail-heading";
  const title = node(heading, "div");
  node(title, "h2", "Solicitação de " + r.tipo.toLowerCase());
  node(title, "p", "Protocolo " + r.protocolo);
  button(heading, "Voltar à lista", async () => {
    el.hidden = true;
    selectedRequest = null;
    await list();
    $("lista").focus();
  }).className = "secondary";
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
    data: r.data_solicitada ? new Intl.DateTimeFormat("pt-BR").format(new Date(r.data_solicitada + "T12:00:00")) : null,
    horário: r.horario_solicitado?.slice(0, 5),
    justificativa: r.justificativa,
    situação: r.status,
    etapa: r.etapa,
    mensagem: r.mensagem,
  })) {
    if (v) {
      const field = node(facts, "div");
      if (["justificativa", "mensagem"].includes(k)) field.className = "wide-fact";
      node(field, "dt", labels[k] || k[0].toUpperCase() + k.slice(1));
      node(field, "dd", v);
    }
  }
  if (r.status === "APROVADA" && ["saida","saída"].includes(r.tipo.toLowerCase())) {
    node(el, "h3", "Conferência da saída");
    for (const [step, entry] of Object.entries(r.confirmacoes)) {
      const title =
        step === "recepção"
          ? "Recepção · conferência"
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
  if (["coordenação", "superusuário"].includes(user.perfil) && (isExit || r.tipo.toLowerCase() === "entrada")) {
    const decision = node(el, "div");
    decision.className = "decision";
    const awaiting = ["PENDENTE", "RECEBIDA"].includes(r.status);
    node(decision, "h3", awaiting ? "Análise da solicitação" : "Revisão da análise");
    node(decision, "p", awaiting
      ? "Confira a identidade, os dados declarados e a autorização do responsável antes de decidir."
      : isExit ? "Reabrir a análise invalida as duas confirmações. Corrigir a recepção também invalida a portaria."
        : "A reabertura devolve o pedido de entrada para análise. O histórico da decisão anterior será preservado.");
    const form = node(decision, "form");
    let msg;
    if (awaiting) {
      const group = node(form, "div");
      const label = node(group, "label", "Mensagem ao solicitante");
      msg = node(label, "textarea");
      msg.name = "mensagem";
      msg.maxLength = 2000;
      msg.setAttribute("aria-describedby", "ajuda-decisao");
      const help = node(group, "small", "Informe o motivo ao recusar. Essa mensagem fica disponível na consulta pelo código.");
      help.id = "ajuda-decisao";
      help.className = "form-help";
    }
    const noteGroup = node(form, "div");
    const label = node(noteGroup, "label", awaiting ? "Observação interna (opcional)" : "Justificativa da revisão (obrigatória)");
    const note = node(label, "textarea");
    note.name = "nota";
    note.maxLength = 2000;
    note.required = !awaiting;
    note.setAttribute("aria-describedby", "ajuda-nota");
    const noteHelp = node(noteGroup, "small", "Visível apenas à coordenação e ao superusuário.");
    noteHelp.id = "ajuda-nota";
    noteHelp.className = "form-help";
    const actions = node(form, "div");
    actions.className = "decision-actions";
    const options = awaiting ? [["aprovar", "Aprovar solicitação"], ["reprovar", "Recusar solicitação"]] : [["reabrir análise", "Reabrir análise"]];
    if (!awaiting && isExit && r.etapa !== "aguardando") options.push(["corrigir recepção", "Corrigir recepção"]);
    if (!awaiting && isExit && r.etapa === "saída concluída") options.push(["corrigir portaria", "Corrigir portaria"]);
    for (const [action, text] of options) {
      const submit = node(actions, "button", text);
      submit.type = "submit";
      submit.value = action;
      if (action === "reprovar") submit.className = "danger";
      else if (!awaiting) submit.className = "secondary";
      submit.onclick = () => { if (msg) msg.required = action === "reprovar"; };
    }
    form.onsubmit = (event) => {
      event.preventDefault();
      run(() => send(event.submitter.value, { nota: note.value, mensagem: msg?.value || "" }));
    };
  }
  if (isExit && r.status === "APROVADA" && (
    (user.perfil === "recepção" && r.etapa === "aguardando") ||
    (user.perfil === "portaria" && r.etapa === "recepção confirmada")
  )) {
    const box = node(
      node(
        el,
        "label",
        user.perfil === "recepção"
          ? "Conferi a autorização na recepção "
          : "Confirmo que o aluno deixou o campus ",
      ),
      "input",
    );
    box.type = "checkbox";
    const save = button(el, "Registrar confirmação", () => send(user.perfil));
    save.disabled = true;
    box.onchange = () => (save.disabled = !box.checked);
  }
  node(el, "h3", "Histórico · horário de Fortaleza");
  for (const e of r.historico.itens) {
    const entry = node(el, "article");
    node(entry, "strong", e.acao);
    node(entry, "small", [e.quando, e.autor].filter(Boolean).join(" · ")).className = "history-meta";
    if (e.nota) node(entry, "p", e.nota).className = "history-note";
  }
  pager(el, page, r.historico.mais, (p) => detail(id, p));
  el.focus({ preventScroll: true });
  el.scrollIntoView({ block: "start" });
}
function roleHelp() {
  const descriptions = {
    "coordenação": "Analisa e aprova ou recusa solicitações de entrada e saída.",
    "recepção": "Confere autorizações de saída aprovadas.",
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

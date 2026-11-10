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
if ($("pedido")) {
  const form = $("pedido");
  function movementGuide() {
    const entry = form.elements.tipo.value === "Entrada";
    $("guia-entrada").hidden = !entry;
    $("guia-saida").hidden = entry;
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
      ("Solicitação salva. " + (body.tipo === "Entrada" ? "Pedido de entrada recebido." : "O envio ainda não autoriza a saída.")) + " Guarde seu código.\nCódigo de consulta: " +
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
    $("resultado").textContent = [
      r.tipo,
      r.status,
      r.status === "APROVADA" ? r.etapa : "",
      r.mensagem,
    ]
      .filter(Boolean)
      .join(" · ");
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
  $("conta").onreset = () => {
    $("conta").elements.id.value = "";
  };
  bind("filtro-contas", () => audit());
  bind("conta", async (body) => {
    body.ativo = $("conta").elements.ativo.checked;
    if (body.id) body.id = Number(body.id);
    else delete body.id;
    await api("contas", body);
    $("conta").reset();
    await accounts();
    await audit();
    $("aviso").textContent = "Conta salva.";
  });
  run(async () => {
    const response = await fetch("/api/me");
    if (response.status === 401) return;
    if (!response.ok) throw Error("Não foi possível carregar o painel.");
    user = await response.json();
    $("entrada").hidden = true;
    $("painel").hidden = false;
    $("perfil").textContent = "Painel de " + user.perfil + " · " + user.nome;
    await list();
    if (user.perfil === "superusuário") {
      $("admin").hidden = false;
      await accounts();
      await audit();
    }
  });
}
async function list(page = 1) {
  const p = new URLSearchParams(fields($("filtro")));
  p.set("pagina", page);
  const r = await api("pedidos?" + p);
  const el = $("lista");
  el.replaceChildren();
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
        ? item.status + " · " + item.etapa
        : item.status,
    );
    status.className = "badge";
    status.dataset.status = item.status;
    button(line, "Abrir detalhes", () => detail(item.id));
  }
  pager(el, page, r.mais, list);
}
async function detail(id, page = 1) {
  const r = await api("pedidos/" + id + "?pagina=" + page),
    el = $("detalhe");
  el.hidden = false;
  el.replaceChildren();
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
  if (
    ["coordenação", "superusuário"].includes(user.perfil) &&
    ["saida", "saída"].includes(r.tipo.toLowerCase())
  ) {
    const note = node(
      node(el, "label", "Observação interna ou justificativa da correção"),
      "textarea",
    );
    note.maxLength = 2000;
    if (r.status === "PENDENTE") {
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
      for (const a of ["aprovar", "reprovar"])
        button(el, a, () => send(a, { nota: note.value, mensagem: msg.value }));
    } else {
      node(
        el,
        "p",
        "Reabrir a análise invalida as duas confirmações. Corrigir a recepção também invalida a portaria.",
      );
      const actions = ["reabrir análise"];
      if (r.etapa !== "aguardando") actions.push("corrigir recepção");
      if (r.etapa === "saída concluída") actions.push("corrigir portaria");
      for (const a of actions)
        button(el, a, () => send(a, { nota: note.value }));
    }
  }
  if (
    (user.perfil === "recepção" && r.etapa === "aguardando") ||
    (user.perfil === "portaria" && r.etapa === "recepção confirmada")
  ) {
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
  for (const e of r.historico.itens)
    node(
      el,
      "article",
      [e.quando, e.acao, e.autor, e.nota].filter(Boolean).join(" · "),
    );
  pager(el, page, r.historico.mais, (p) => detail(id, p));
  el.scrollIntoView();
}
async function accounts(page = 1) {
  const r = await api("contas?pagina=" + page),
    el = $("contas");
  el.replaceChildren();
  for (const a of r.itens) {
    const line = node(
      el,
      "article",
      a.nome + " · " + a.perfil + " · " + (a.ativo ? "Ativa" : "Inativa") + " ",
    );
    button(line, "Editar", () => {
      const f = $("conta");
      f.reset();
      for (const k of ["id", "nome", "email", "perfil"])
        f.elements[k].value = a[k];
      f.elements.ativo.checked = a.ativo;
      f.elements.nome.focus();
    });
  }
  pager(el, page, r.mais, accounts);
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

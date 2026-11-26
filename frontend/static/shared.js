const $ = (id) => document.getElementById(id);
const snowToggle = $("neve");
snowToggle.hidden = false;
snowToggle.onclick = async () => {
  const { toggleSnow } = await import(snowToggle.dataset.module);
  toggleSnow(snowToggle);
};
const fields = (form) => Object.fromEntries(new FormData(form));
const isRecord = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const confirmsWrite = (data) => data.ok === true;
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
async function api(path, body, validate) {
  const opts = body
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-SISGECE": "1" },
        body: JSON.stringify(body),
      }
    : {};
  const unavailable = body
    ? "O servidor está indisponível. Não foi possível confirmar o envio."
    : "O servidor está indisponível. Tente novamente em instantes.";
  let response;
  try {
    response = await fetch("/api/" + path, opts);
  } catch {
    throw Error(body
      ? "A conexão com o servidor falhou. Não foi possível confirmar o envio."
      : "Não foi possível conectar ao servidor. Verifique a conexão e tente novamente.");
  }
  if (response.status >= 500) throw Error(unavailable);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = typeof data?.erro === "string" && data.erro.trim()
      ? data.erro : "Não foi possível concluir a operação.";
    throw Object.assign(Error(message), { status: response.status });
  }
  if (!isRecord(data) || (validate && !validate(data))) {
    throw Error(body
      ? "O servidor respondeu de forma inesperada. Não foi possível confirmar o envio."
      : "O servidor respondeu de forma inesperada. Tente novamente em instantes.");
  }
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

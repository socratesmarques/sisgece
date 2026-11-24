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
    const submit = $("enviar-pedido");
    const status = $("pedido-status");
    submit.disabled = true;
    submit.textContent = "Enviando solicitação…";
    form.setAttribute("aria-busy", "true");
    status.dataset.state = "loading";
    status.textContent = "Enviando solicitação…";
    $("recibo").textContent = "";
    try {
      await api("solicitar", body, confirmsWrite);
      $("recibo").textContent =
        "Solicitação enviada com sucesso! O pedido será analisado pela coordenação." +
        (form.dataset.whatsappAuto === "true"
          ? " Acompanhe as atualizações do processo pelo WhatsApp no número informado."
          : "");
      status.textContent = "";
      delete status.dataset.state;
      form.reset();
      form.origem.onchange();
      $("recibo").focus();
    } catch (error) {
      status.dataset.state = "error";
      status.textContent = error.message || "Não foi possível enviar a solicitação.";
      status.focus();
    } finally {
      submit.disabled = false;
      submit.textContent = "Enviar solicitação";
      form.removeAttribute("aria-busy");
    }
  });
}

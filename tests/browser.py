"""Smoke de navegador em uma instalação exclusiva de testes com LOCAL_HTTP=1."""
import os
from playwright.sync_api import sync_playwright, expect

url=os.getenv("TEST_URL","http://127.0.0.1:8004")
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel=os.getenv("BROWSER_CHANNEL") or None)
    for width,role in [(1280,"Aluno"),(390,"Responsável")]:
        page=browser.new_page(viewport={"width":width,"height":844})
        page.goto(url)
        form=page.locator("#pedido")
        form.locator("select").select_option(role)
        values=dict(aluno="Teste navegador",responsavel="Responsável fictício",matricula="TEST-X",telefone="85999999999",data="2030-01-21",hora="15:00",justificativa="Validação do navegador")
        if role=="Responsável":
            values.update(cpf="12345678901",parentesco="Mãe")
        for k,v in values.items():
            form.locator(f"[name={k}]").fill(v)
        form.get_by_role("button").click()
        receipt=page.locator("#recibo")
        expect(receipt).to_contain_text("Solicitação salva")
        lines=receipt.inner_text().splitlines()
        page.locator("#rastrear [name=protocolo]").fill(lines[-2].split(": ")[1])
        page.locator("#rastrear [name=codigo]").fill(lines[-1].split(": ")[1])
        page.get_by_role("button",name="Consultar solicitação").click()
        expect(page.locator("#resultado")).to_contain_text("PENDENTE")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.close()
    browser.close()
    print("Envio e acompanhamento aprovados em 1280 e 390 px.")


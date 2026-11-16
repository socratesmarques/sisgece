"""Smoke de navegador em uma instalação exclusiva de testes com LOCAL_HTTP=1."""

import os
import secrets
from playwright.sync_api import sync_playwright, expect

url = os.getenv("TEST_URL", "http://127.0.0.1:8004")
with sync_playwright() as pw:
    browser = pw.chromium.launch(channel=os.getenv("BROWSER_CHANNEL") or None)
    for width, role in [(1280, "Aluno"), (390, "Responsável")]:
        page = browser.new_page(viewport={"width": width, "height": 844})
        page.goto(url)
        form = page.locator("#pedido")
        form.locator("select").select_option(role)
        values = dict(
            aluno="Teste navegador",
            responsavel="Responsável fictício",
            matricula="TEST-"+secrets.token_hex(5),
            telefone="85999999999",
            data="2030-01-21",
            hora="15:00",
            justificativa="Validação do navegador",
        )
        if role == "Responsável":
            values.update(cpf="12345678901", parentesco="Mãe")
        for k, v in values.items():
            form.locator(f"[name={k}]").fill(v)
        form.get_by_role("button").click()
        receipt = page.locator("#recibo")
        expect(receipt).to_contain_text("Solicitação salva")
        lines = receipt.inner_text().splitlines()
        page.locator("#rastrear [name=codigo]").fill(lines[-1].split(": ")[1])
        page.get_by_role("button", name="Consultar solicitação").click()
        expect(page.locator("#resultado")).to_contain_text("PENDENTE")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.close()
    browser.close()
    print("Envio e acompanhamento aprovados em 1280 e 390 px.")


# A instalação usada aqui deve ser exclusiva de testes: criamos contas reais no banco.
import secrets
import psycopg
from werkzeug.security import generate_password_hash
from playwright.sync_api import sync_playwright, expect

suffix = secrets.token_hex(6)
password = secrets.token_urlsafe()
roles = ("coordenação", "recepção", "portaria")
with psycopg.connect() as db:
    for role in roles:
        db.execute(
            "INSERT INTO administradores(nome,usuario,senha_hash,perfil) VALUES (%s,%s,%s,%s)",
            (
                role,
                str(roles.index(role)) + suffix,
                generate_password_hash(password),
                role,
            ),
        )

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel=os.getenv("BROWSER_CHANNEL") or None)
    for width, role in zip((1280, 390, 390), roles):
        page = browser.new_page(viewport={"width": width, "height": 844})
        page.goto(url + "/equipe")
        page.get_by_label("Usuário", exact=True).first.fill(
            str(roles.index(role)) + suffix
        )
        page.get_by_label("Senha", exact=True).fill(password)
        page.get_by_role("button", name="Entrar").click()
        page.locator("#filtro [name=q]").fill(values["matricula"])
        page.get_by_role("button", name="Buscar solicitações").click()
        page.get_by_role("button", name="Abrir detalhes").first.click()
        if role == "coordenação":
            page.get_by_role("button", name="Aprovar solicitação", exact=True).click()
        else:
            page.locator("#detalhe input[type=checkbox]").check()
            page.get_by_role("button", name="Registrar confirmação").click()
        expect(page.locator("#aviso")).to_have_text("Ação registrada.")
        if role == "portaria":
            expect(page.locator("#detalhe")).to_contain_text("saída concluída")
        page.close()
    browser.close()
print("Aprovação, recepção e portaria verificadas na interface.")

# Regressão: entradas precisam aceitar decisões nos dois perfis de análise.
# Os dados abaixo são fictícios e pertencem apenas à instalação de testes.
with psycopg.connect() as db:
    db.execute(
        "INSERT INTO administradores(nome,usuario,senha_hash,perfil) VALUES (%s,%s,%s,%s)",
        ("Superusuário de teste", "admin" + suffix, generate_password_hash(password), "superusuário"),
    )


def assert_responsive(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Rolagem horizontal inesperada"


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel=os.getenv("BROWSER_CHANNEL") or None)
    errors = []
    def new_page(**options):
        page = browser.new_page(**options)
        page.on("pageerror", lambda error: errors.append(str(error)))
        return page
    for role, username, width in (("coordenação", "0" + suffix, 1280), ("superusuário", "admin" + suffix, 390)):
        staff = new_page(viewport={"width": width, "height": 844})
        staff.goto(url + "/equipe")
        staff.get_by_label("Usuário", exact=True).fill(username)
        staff.get_by_label("Senha", exact=True).fill(password)
        staff.get_by_role("button", name="Entrar", exact=True).click()
        expect(staff.locator("#painel")).to_be_visible()
        for action, expected in (("Aprovar solicitação", "APROVADA"), ("Recusar solicitação", "REPROVADA")):
            public = new_page(viewport={"width": width, "height": 844})
            public.goto(url)
            public.wait_for_load_state("networkidle")
            form = public.locator("#pedido")
            form.get_by_role("radio", name="Entrada Acesso ao campus", exact=True).check()
            expect(public.locator("#guia-entrada")).to_be_visible()
            entry = dict(values, aluno="Aluno " + "L" * 194, matricula="ENTRADA-" + secrets.token_hex(5), justificativa="Atendimento de teste no campus")
            for key, value in entry.items():
                if key not in ("cpf", "parentesco"):
                    form.locator(f"[name={key}]").fill(value)
            form.get_by_role("button", name="Enviar solicitação").click()
            expect(public.locator("#recibo")).to_contain_text("aguarda análise")
            public.get_by_role("button", name="Consultar solicitação").click()
            expect(public.locator("#resultado")).to_contain_text("PENDENTE")
            staff.locator("#filtro [name=q]").fill(entry["matricula"])
            staff.locator("#filtro [name=tipo]").select_option("Entrada")
            staff.get_by_role("button", name="Buscar solicitações").click()
            expect(staff.locator("#lista .record")).to_have_count(1)
            staff.get_by_role("button", name="Abrir detalhes").click()
            detail = staff.locator("#detalhe")
            expect(detail.get_by_role("heading", name="Análise da solicitação")).to_be_visible()
            if expected == "REPROVADA":
                detail.get_by_role("button", name=action, exact=True).click()
                assert detail.locator("[name=mensagem]").evaluate("el => !el.checkValidity()")
                expect(detail.get_by_role("heading", name="Análise da solicitação")).to_be_visible()
            detail.get_by_label("Mensagem ao solicitante", exact=True).fill("Orientação pública de teste")
            detail.get_by_label("Observação interna (opcional)", exact=True).fill("NOTA INTERNA RESERVADA")
            detail.get_by_role("button", name=action, exact=True).click()
            expect(staff.locator("#aviso")).to_have_text("Ação registrada.")
            expect(detail).to_contain_text(expected)
            expect(detail.get_by_role("button", name="Corrigir recepção")).to_have_count(0)
            expect(detail.get_by_role("button", name="Corrigir portaria")).to_have_count(0)
            public.get_by_role("button", name="Consultar solicitação").click()
            result = public.locator("#resultado")
            expect(result).to_contain_text(expected)
            expect(result).to_contain_text("Orientação pública de teste")
            expect(result).not_to_contain_text("NOTA INTERNA RESERVADA")
            expect(result).not_to_contain_text("null")
            assert_responsive(public)
            assert_responsive(staff)
            detail.get_by_label("Justificativa da revisão (obrigatória)").fill("Revisar dados de teste")
            detail.get_by_role("button", name="Reabrir análise", exact=True).click()
            expect(detail.get_by_role("heading", name="Análise da solicitação")).to_be_visible()
            public.get_by_role("button", name="Consultar solicitação").click()
            expect(result).to_contain_text("PENDENTE")
            expect(result).not_to_contain_text("Orientação pública de teste")
            public.close()
        for width in (320, 390, 768, 1024, 1440):
            staff.set_viewport_size({"width": width, "height": 900})
            assert_responsive(staff)
            staff.get_by_role("button", name="Histórico", exact=True).click()
            expect(staff.locator("#historico-pedidos")).to_be_visible()
            assert_responsive(staff)
            staff.get_by_role("button", name="Solicitações", exact=True).click()
            if role == "superusuário":
                staff.get_by_role("button", name="Funcionários", exact=True).click()
                expect(staff.locator("#admin")).to_be_visible()
                assert_responsive(staff)
                staff.get_by_role("button", name="Adicionar funcionário").click()
                expect(staff.locator("#editor")).to_be_visible()
                assert_responsive(staff)
                assert staff.locator("#editor").evaluate("el => el.scrollWidth <= el.clientWidth"), "Conteúdo do diálogo excede a largura"
                staff.keyboard.press("Escape")
                expect(staff.locator("#editor")).not_to_be_visible()
                staff.get_by_role("button", name="Solicitações", exact=True).click()
        staff.close()
    for width in (320, 390, 768, 1024, 1440):
        page = new_page(viewport={"width": width, "height": 900})
        page.goto(url)
        page.wait_for_load_state("networkidle")
        assert_responsive(page)
        page.keyboard.press("Tab")
        expect(page.locator(".skip")).to_be_focused()
        page.keyboard.press("Enter")
        expect(page.locator("#principal")).to_be_focused()
        page.locator("#pedido [name=origem]").select_option("Responsável")
        expect(page.locator("#familia")).to_be_visible()
        assert_responsive(page)
        page.goto(url + "/equipe")
        page.wait_for_load_state("networkidle")
        expect(page.locator("#entrada")).to_be_visible()
        assert_responsive(page)
        page.close()
    assert not errors, errors
    browser.close()
print("Entradas: aprovação, recusa e reabertura verificadas para coordenação e superusuário.")
print("Responsividade: página pública, login, painel, detalhes, histórico, funcionários e diálogo em 320, 390, 768, 1024 e 1440 px.")

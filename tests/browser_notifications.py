"""Smoke da interface sem checkboxes; modo mock jamais ativa envios implícitos."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright, expect

assert os.getenv('NOTIFICATIONS_PROVIDER', 'mock') == 'mock'
url = os.getenv('TEST_URL', 'http://127.0.0.1:8004')

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
    for width in (390, 1280):
        page = browser.new_page(viewport={'width':width, 'height':900})
        page.goto(url)
        form = page.locator('#pedido')
        expect(form.locator('[name=whatsapp_consent]')).to_have_count(0)
        expect(form.locator('[name=whatsapp_feedback_consent]')).to_have_count(0)
        expect(form.locator('.whatsapp-notice')).to_be_visible()
        for key, value in dict(aluno='Teste WhatsApp', matricula='MOCK',
                               responsavel='Fictício', telefone='85987654321',
                               data='2030-01-01', hora='12:00',
                               justificativa='Teste').items():
            form.locator('[name='+key+']').fill(value)

        def unavailable_submission(route):
            route.fulfill(status=503, content_type='text/html', body='<h1>Service unavailable</h1>')

        def invalid_receipt(route):
            route.fulfill(status=201, json={'ok': False})

        submit = form.get_by_role('button', name='Enviar solicitação')
        for handler, message in (
            (unavailable_submission, 'O servidor está indisponível. Não foi possível confirmar o envio.'),
            (invalid_receipt, 'O servidor respondeu de forma inesperada. Não foi possível confirmar o envio.'),
        ):
            page.route('**/api/solicitar', handler)
            submit.click()
            expect(page.locator('#pedido-status')).to_have_text(message)
            expect(page.locator('#recibo')).to_be_empty()
            expect(form.locator('[name=aluno]')).to_have_value('Teste WhatsApp')
            expect(submit).to_be_enabled()
            page.unroute('**/api/solicitar', handler)
        with page.expect_response(lambda response: response.url.endswith('/api/solicitar') and response.request.method == 'POST') as submitted:
            submit.click()
        receipt = page.locator('#recibo')
        expect(receipt).to_contain_text('Solicitação enviada com sucesso!')
        expect(receipt).not_to_contain_text('WhatsApp')
        expect(page.locator('#copiar')).to_have_count(0)
        expect(page.locator('#whatsapp-status')).to_have_count(0)
        assert submitted.value.status == 201
        assert submitted.value.json() == {'ok': True}
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.close()
    browser.close()
print('Interface sem checkboxes e modo mock sem inscrições implícitas aprovados.')

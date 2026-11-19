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
        form.get_by_role('button', name='Enviar solicitação').click()
        expect(page.locator('#recibo')).to_contain_text('Solicitação salva')
        code = page.locator('#recibo').inner_text().splitlines()[-1].split(': ')[1]
        response = page.request.post(url+'/api/consulta', data={'codigo':code},
                                     headers={'X-SISGECE':'1'})
        assert response.status == 200
        assert response.json()['status'] == 'PENDENTE'
        # No mock CI, o modo laboratório automático não é habilitado.
        state = page.request.post(url+'/api/notificacoes/estado',
                                  data={'codigo':code}, headers={'X-SISGECE':'1'})
        assert state.status == 200
        assert state.json()['estado'] == 'sem autorização'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.close()
    browser.close()
print('Interface sem checkboxes e modo mock sem inscrições implícitas aprovados.')

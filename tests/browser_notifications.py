"""Smoke opt-in exclusivamente em instalação mock descartável."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
import psycopg
from psycopg.rows import dict_row
from backend.notifications.consent import confirm
from backend.notifications.providers import MockProvider
from backend.notifications.worker import process_one

assert os.getenv('NOTIFICATIONS_PROVIDER','mock')=='mock'
url = os.getenv('TEST_URL','http://127.0.0.1:8004')
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=os.getenv('BROWSER_EXECUTABLE') or None)
    for width in (390,1280):
        page = browser.new_page(viewport={'width':width,'height':900})
        page.add_init_script("""
            const originalFetch = window.fetch.bind(window);
            const gate = new Promise(resolve => { window.resumeNotificationStatus = resolve; });
            window.fetch = async (...args) => {
                if (String(args[0]).includes('notificacoes/estado')) await gate;
                return originalFetch(...args);
            };
        """)
        page.goto(url)
        form = page.locator('#pedido')
        expect(form.locator('[name=whatsapp_consent]')).not_to_be_checked()
        expect(form).to_contain_text('Modo de simulação')
        for key,value in dict(aluno='Teste WhatsApp',matricula='MOCK',responsavel='Fictício',
                              telefone='85987654321',data='2030-01-01',hora='12:00',justificativa='Teste').items():
            form.locator('[name='+key+']').fill(value)
        form.locator('[name=whatsapp_recipient]').select_option('solicitante')
        form.locator('[name=whatsapp_consent]').check()
        form.get_by_role('button',name='Enviar solicitação').click()
        expect(page.locator('#recibo')).to_contain_text('Solicitação salva')
        # A consulta principal funciona enquanto a consulta auxiliar está bloqueada.
        page.get_by_role('button',name='Consultar solicitação').click()
        expect(page.locator('#resultado')).to_contain_text('PENDENTE')
        page.evaluate('window.resumeNotificationStatus()')
        status = page.locator('#whatsapp-status')
        expect(status).to_contain_text('aguardando confirmação')
        expect(status).to_contain_text('Solicitante')
        expect(status).not_to_contain_text('85987654321')
        status.get_by_role('button',name='Confirmar número no WhatsApp').click()
        expect(status.locator('code')).to_contain_text('CONFIRMAR ')
        token = status.locator('code').inner_text().split()[1]
        with psycopg.connect(row_factory=dict_row) as conn:
            assert confirm(conn,token,'5585987654321','mock')
            conn.execute('TRUNCATE notificacao_ritmo')
        status.get_by_role('button',name='Atualizar confirmação').click()
        expect(status).to_contain_text('ativa')
        provider = MockProvider()
        assert process_one(provider)
        assert len(provider.messages)==1
        status.get_by_role('button',name='Revogar notificações').click()
        expect(status).to_contain_text('revogada')
        page.get_by_role('button',name='Consultar solicitação').click()
        expect(page.locator('#resultado')).to_contain_text('PENDENTE')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.close()
    browser.close()
print('WhatsApp mock: consentimento, confirmação, worker, revogação e consulta em 390/1280 px aprovados.')

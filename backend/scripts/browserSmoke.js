// Executado pela CI contra uma instalação descartável, com registros preparados pelo workflow.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
async function verificar() {
    const base = process.env.BROWSER_BASE_URL || 'http://localhost:8004';
    const email = process.env.TEST_ADMIN_EMAIL;
    const senha = process.env.TEST_ADMIN_PASSWORD;
    assert.ok(email && senha, 'Defina credenciais exclusivas de teste');
    fs.mkdirSync('browser-results', { recursive: true });
    const browser = await chromium.launch();
    const errors = [];
    try {
        const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
        const page = await context.newPage();
        page.setDefaultTimeout(15000);
        page.on('pageerror', error => errors.push(error.message));
        page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
        page.on('dialog', async dialog => {
            if (dialog.type() === 'prompt') await dialog.accept('Conferido na CI');
            else { errors.push('Diálogo inesperado: ' + dialog.message()); await dialog.dismiss(); }
        });
        await page.goto(base);
        await page.locator('#email').fill(email);
        await page.locator('#senha').fill(senha);
        await page.getByRole('button', { name: 'Entrar', exact: true }).click();
        await page.waitForURL('**/admin-dashboard.html');
        await page.locator('#usuario').filter({ hasText: 'Coordenador' }).waitFor();
        const cookies = await context.cookies();
        assert.ok(cookies.some(c => c.name === 'sisgece_session' && c.httpOnly && c.secure && c.sameSite === 'Strict'));
        const form = page.locator('#solicitacao-form');
        await form.locator('[name=matricula]').fill('ci-20260001');
        await form.locator('[name=justificativa]').fill('<img src=x onerror=alert(1)> Consulta de teste');
        await form.locator('[name=data_solicitada]').fill('2026-11-10');
        await form.locator('[name=horario_solicitado]').fill('14:30');
        await form.getByRole('button', { name: 'Salvar solicitação' }).click();
        await page.locator('#solicitacoes article').waitFor();
        assert.equal(await page.locator('#solicitacoes img').count(), 0);
        await page.screenshot({ path: 'browser-results/desktop.png', fullPage: true });
        await page.getByRole('button', { name: 'Aprovar', exact: true }).click();
        await page.getByText('Nenhuma solicitação encontrada.').waitFor();
        await page.locator('#historico').check();
        await page.locator('#solicitacoes article').filter({ hasText: 'APROVADA' }).waitFor();
        await page.setViewportSize({ width: 390, height: 844 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        await page.screenshot({ path: 'browser-results/mobile.png', fullPage: true });
        await page.getByRole('button', { name: 'Sair', exact: true }).click();
        await page.waitForURL('**/admin-login.html');
        assert.equal((await context.request.get(base + '/auth/me')).status(), 401);
        assert.deepEqual(errors, []);
        console.log('Fluxo de navegador OK: login, criação, escape de HTML, aprovação, histórico, mobile e logout.');
    } finally { await browser.close(); }
}
verificar().catch(error => { console.error(error); process.exitCode = 1; });

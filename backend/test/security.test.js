const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
process.env.JWT_SECRET = 'test-only-secret-with-at-least-32-characters';
process.env.NODE_ENV = 'production';
const jwt = require('jsonwebtoken');
const pool = require('../src/config/database');
const app = require('../app');
let server, base, consultas = 0;
const originalQuery = pool.query;
before(async () => {
    pool.query = async () => { consultas++; throw new Error('Banco indisponível para teste'); };
    server = app.listen(0, '127.0.0.1');
    await new Promise(resolve => server.once('listening', resolve));
    base = 'http://127.0.0.1:' + server.address().port;
});
after(async () => {
    pool.query = originalQuery;
    await new Promise(resolve => server.close(resolve));
    await pool.end();
});
const json = value => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) });
test('recusa iniciar sem chave JWT forte', () => {
    const result = spawnSync(process.execPath, ['-e', "require('./src/config/runtime')"], {
        cwd: require('node:path').join(__dirname, '..'), env: { ...process.env, JWT_SECRET: 'curta' }
    });
    assert.notEqual(result.status, 0);
});
test('recusa confiança global em cabeçalhos de proxy', () => {
    for (const proxy of ['true', '0.0.0.0/0', '::/0']) {
        const result = spawnSync(process.execPath, ['-e', "require('./src/config/runtime')"], {
            cwd: require('node:path').join(__dirname, '..'), env: { ...process.env, TRUST_PROXY: proxy }
        });
        assert.notEqual(result.status, 0, proxy);
    }
});
test('produção abre painel real e bloqueia demonstração', async () => {
    const res = await fetch(base, { redirect: 'manual' });
    assert.equal(res.status, 302);
    assert.equal(res.headers.get('location'), '/pages/admin-login.html');
    for (const path of ['/demo', '/assets/js/app.js', '/assets/js/%61pp.js', '/backend/.env']) {
        assert.equal((await fetch(base + path)).status, 404, path);
    }
});
test('dados e escritas exigem autenticação antes de consultar banco', async () => {
    const antes = consultas;
    for (const path of ['/estudantes', '/estudantes/123', '/responsaveis/123', '/solicitacoes', '/solicitacoes/pendentes']) {
        const res = await fetch(base + path);
        assert.equal(res.status, 401, path);
        assert.equal(res.headers.get('cache-control'), 'no-store');
    }
    assert.equal((await fetch(base + '/solicitacoes', json({ estudante_id: 1 }))).status, 401);
    assert.equal(consultas, antes);
});
test('recusa JWT antigo, adulterado e com audiência incorreta', async () => {
    for (const token of ['invalido', jwt.sign({ id: 1 }, process.env.JWT_SECRET),
        jwt.sign({ id: 1 }, process.env.JWT_SECRET, { issuer: 'sisgece', audience: 'outro' })]) {
        assert.equal((await fetch(base + '/auth/me', { headers: { Authorization: 'Bearer ' + token } })).status, 401);
    }
});
test('recusa CSRF, formulário, JSON inválido e corpo grande com erros controlados', async () => {
    assert.equal((await fetch(base + '/auth/login', { method: 'POST', body: 'email=x' })).status, 415);
    assert.equal((await fetch(base + '/auth/logout', { ...json({}), headers: { ...json({}).headers, 'Sec-Fetch-Site': 'cross-site' } })).status, 403);
    assert.equal((await fetch(base + '/auth/login', { ...json({}), body: '{' })).status, 400);
    assert.equal((await fetch(base + '/auth/login', json({ senha: 'x'.repeat(40000) }))).status, 413);
    assert.equal((await fetch(base + '/auth/login', json({ email: {}, senha: [] }))).status, 400);
});
test('falha de prontidão retorna 503 sem detalhes do banco', async () => {
    const res = await fetch(base + '/api/ready');
    assert.equal(res.status, 503);
    assert.deepEqual(await res.json(), { status: 'indisponivel' });
});
test('envia cabeçalhos de segurança e limita tentativas de login', async () => {
    const res = await fetch(base + '/pages/admin-login.html');
    assert.match(res.headers.get('content-security-policy'), /script-src 'self'/);
    assert.equal(res.headers.get('x-content-type-options'), 'nosniff');
    assert.equal(res.headers.get('x-powered-by'), null);
    let limitado;
    for (let i = 0; i < 12; i++) limitado = await fetch(base + '/auth/login', json({}));
    assert.equal(limitado.status, 429);
    assert.ok(limitado.headers.get('retry-after'));
});

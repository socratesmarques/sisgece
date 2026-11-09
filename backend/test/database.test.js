const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
// Use exclusivamente um banco descartável cujo nome termina em _test.
test('fluxo HTTP com PostgreSQL real: sessão, validação, criação e decisões', {
    skip: process.env.RUN_DATABASE_TESTS !== '1'
}, async t => {
    assert.match(process.env.PGDATABASE || '', /_test$/, 'Exige banco descartável terminado em _test');
    process.env.JWT_SECRET = 'isolated-test-secret-at-least-32-characters';
    process.env.NODE_ENV = 'production';
    const bcrypt = require('bcryptjs');
    const jwt = require('jsonwebtoken');
    const pool = require('../src/config/database');
    const app = require('../app');
    const server = app.listen(0, '127.0.0.1');
    await new Promise(resolve => server.once('listening', resolve));
    const base = 'http://127.0.0.1:' + server.address().port;
    const json = data => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
    let adminId, estudanteId, responsavelId, cookie;
    const email = `teste-${Date.now()}@example.com`;
    try {
        await pool.query(fs.readFileSync(path.join(__dirname, '../../db/init/001_schema.sql'), 'utf8'));
        adminId = (await pool.query('INSERT INTO administradores (nome,email,senha_hash) VALUES ($1,$2,$3) RETURNING id',
            ['Admin de teste', email, await bcrypt.hash('senha-de-teste-segura', 12)])).rows[0].id;
        estudanteId = (await pool.query('INSERT INTO estudantes (nome,matricula) VALUES ($1,$2) RETURNING id',
            ['<img src=x onerror=alert(1)>', `teste-${Date.now()}`])).rows[0].id;
        responsavelId = (await pool.query('INSERT INTO responsaveis (nome,cpf) VALUES ($1,$2) RETURNING id',
            ['Responsável de teste', `teste-${Date.now()}`])).rows[0].id;
        const auth = options => ({ ...options, headers: { ...options?.headers, Cookie: cookie } });
        await t.test('prontidão verifica tabelas reais', async () => {
            assert.equal((await fetch(base + '/api/ready')).status, 200);
        });
        await t.test('login normaliza email, emite cookie seguro e não expõe token no JSON', async () => {
            const res = await fetch(base + '/auth/login', json({ email: ' ' + email.toUpperCase() + ' ', senha: 'senha-de-teste-segura' }));
            assert.equal(res.status, 200);
            const setCookie = res.headers.get('set-cookie');
            for (const attr of ['HttpOnly', 'Secure', 'SameSite=Strict']) assert.ok(setCookie.includes(attr));
            cookie = setCookie.split(';')[0];
            assert.equal((await res.json()).token, undefined);
            assert.equal((await fetch(base + '/auth/me', auth())).status, 200);
        });
        await t.test('valida campos antes da escrita e responsável deve estar vinculado', async () => {
            for (const data of [{ estudante_id: true }, { estudante_id: 2147483648 },
                { data_solicitada: '0000-01-01' }, { estudante_id: [estudanteId] },
                { data_solicitada: '2026-02-30' }, { horario_solicitado: '25:00' },
                { justificativa: ' ' }, { justificativa: 'x'.repeat(2001) }, { tipo: {} }]) {
                const res = await fetch(base + '/solicitacoes', auth(json({ estudante_id: estudanteId,
                    tipo: 'Saída antecipada', justificativa: 'Consulta', ...data })));
                assert.equal(res.status, 400, JSON.stringify(data));
            }
            assert.equal((await fetch(base + '/solicitacoes', auth(json({ estudante_id: estudanteId,
                responsavel_id: responsavelId, tipo: 'Saída antecipada', justificativa: 'Consulta' })))).status, 400);
            assert.equal((await fetch(base + '/solicitacoes/1/aprovar', auth({ ...json([]), method: 'PATCH' }))).status, 400);
        });
        let solicitacaoId;
        await t.test('persiste solicitação com vínculo validado e ignora campos de decisão enviados', async () => {
            await pool.query('INSERT INTO responsavel_estudante VALUES ($1, $2)', [responsavelId, estudanteId]);
            const res = await fetch(base + '/solicitacoes', auth(json({ estudante_id: estudanteId,
                responsavel_id: responsavelId, tipo: 'Saída antecipada', justificativa: '<script>alert(1)</script>',
                data_solicitada: '2026-11-10', horario_solicitado: '14:30', status: 'APROVADA', administrador_id: 999 })));
            assert.equal(res.status, 201);
            const s = (await res.json()).solicitacao;
            solicitacaoId = s.id;
            assert.equal(s.status, 'PENDENTE');
            assert.equal(s.administrador_id, null);
            const lista = await (await fetch(base + '/solicitacoes/pendentes', auth())).json();
            assert.ok(lista.some(s => s.id === solicitacaoId));
        });
        await t.test('decisões concorrentes não sobrescrevem análise e guardam autor real', async () => {
            const respostas = await Promise.all(['aprovar', 'reprovar'].map(acao =>
                fetch(base + `/solicitacoes/${solicitacaoId}/${acao}`, auth({ ...json({ observacao: 'Análise de teste', administrador_id: 999 }), method: 'PATCH' }))));
            assert.deepEqual(respostas.map(r => r.status).sort(), [200, 404]);
            const s = (await pool.query('SELECT * FROM solicitacoes WHERE id = $1', [solicitacaoId])).rows[0];
            assert.equal(s.administrador_id, adminId);
            assert.ok(s.analisado_em);
            assert.equal(s.observacao_coordenacao, 'Análise de teste');
        });
        await t.test('rejeita credenciais erradas e token expirado', async () => {
            assert.equal((await fetch(base + '/auth/login', json({ email, senha: 'incorreta' }))).status, 401);
            const token = jwt.sign({ id: adminId }, process.env.JWT_SECRET, { expiresIn: -1, issuer: 'sisgece', audience: 'sisgece-admin' });
            assert.equal((await fetch(base + '/auth/me', { headers: { Authorization: 'Bearer ' + token } })).status, 401);
        });
        await t.test('desativar administrador invalida imediatamente sua sessão', async () => {
            await pool.query('UPDATE administradores SET ativo = false WHERE id = $1', [adminId]);
            assert.equal((await fetch(base + '/solicitacoes', auth())).status, 401);
        });
        await t.test('logout remove cookie', async () => {
            const res = await fetch(base + '/auth/logout', auth(json({})));
            assert.equal(res.status, 204);
            assert.match(res.headers.get('set-cookie'), /Expires=Thu, 01 Jan 1970/);
        });
    } finally {
        if (estudanteId) {
            await pool.query('DELETE FROM solicitacoes WHERE estudante_id = $1', [estudanteId]);
            await pool.query('DELETE FROM estudantes WHERE id = $1', [estudanteId]);
        }
        if (responsavelId) await pool.query('DELETE FROM responsaveis WHERE id = $1', [responsavelId]);
        if (adminId) await pool.query('DELETE FROM administradores WHERE id = $1', [adminId]);
        await new Promise(resolve => server.close(resolve));
        await pool.end();
    }
});

const jwt = require('jsonwebtoken');
const pool = require('../config/database');
const { secret } = require('../config/runtime');

async function autenticar(req, res, next) {
    const authorization = req.headers.authorization || '';
    const cookie = (req.headers.cookie || '').split(';').map(v => v.trim())
        .find(v => v.startsWith('sisgece_session='));
    const token = authorization.startsWith('Bearer ') ? authorization.slice(7) : cookie?.slice(16);
    if (!token) return res.status(401).json({ erro: 'Autenticação necessária' });
    let dados;
    try {
        dados = jwt.verify(token, secret, {
            algorithms: ['HS256'], issuer: 'sisgece', audience: 'sisgece-admin'
        });
        if (!Number.isSafeInteger(dados.id) || dados.id <= 0) throw new Error('Identidade inválida');
    } catch {
        return res.status(401).json({ erro: 'Sessão inválida ou expirada' });
    }
    try {
        const resultado = await pool.query(
            'SELECT id, nome, email FROM administradores WHERE id = $1 AND ativo = TRUE', [dados.id]
        );
        if (!resultado.rows.length) return res.status(401).json({ erro: 'Sessão inválida ou expirada' });
        req.administrador = resultado.rows[0];
        next();
    } catch (erro) { next(erro); }
}
module.exports = autenticar;

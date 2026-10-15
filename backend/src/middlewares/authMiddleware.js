const jwt = require('jsonwebtoken');

function autenticar(req, res, next) {
    const authorization = req.headers.authorization;

    if (!authorization) {
        return res.status(401).json({
            erro: 'Token não informado'
        });
    }

    const partes = authorization.split(' ');

    if (
        partes.length !== 2 ||
        partes[0] !== 'Bearer'
    ) {
        return res.status(401).json({
            erro: 'Token inválido'
        });
    }

    const token = partes[1];

    try {
        const dados = jwt.verify(
            token,
            process.env.JWT_SECRET
        );

        req.administrador = dados;

        next();

    } catch (erro) {
        return res.status(401).json({
            erro: 'Token inválido ou expirado'
        });
    }
}

module.exports = autenticar;
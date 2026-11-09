const idValido = valor => (typeof valor === 'number' || (typeof valor === 'string' && /^\d+$/.test(valor))) && Number.isSafeInteger(Number(valor)) && Number(valor) > 0 && Number(valor) <= 2147483647;
const textoValido = (valor, max) => typeof valor === 'string' && valor.trim().length > 0 && valor.length <= max;
function validarCriacao(req, res, next) {
    const b = req.body || {};
    const dataValida = !b.data_solicitada || (typeof b.data_solicitada === 'string' &&
        /^\d{4}-\d{2}-\d{2}$/.test(b.data_solicitada) && !b.data_solicitada.startsWith('0000-') &&
        Number.isFinite(Date.parse(b.data_solicitada)) &&
        new Date(b.data_solicitada).toISOString().slice(0, 10) === b.data_solicitada);
    if (!idValido(b.estudante_id) || (b.responsavel_id != null && !idValido(b.responsavel_id)) ||
        !textoValido(b.tipo, 80) || !textoValido(b.justificativa, 2000) || !dataValida ||
        (b.horario_solicitado != null && b.horario_solicitado !== '' &&
         (typeof b.horario_solicitado !== 'string' || !/^([01]\d|2[0-3]):[0-5]\d$/.test(b.horario_solicitado)))) {
        return res.status(400).json({ erro: 'Dados da solicitação inválidos' });
    }
    next();
}
function validarDecisao(req, res, next) {
    const observacao = req.body?.observacao;
    if (!req.body || typeof req.body !== 'object' || Array.isArray(req.body) || !idValido(req.params.id) || (observacao != null && (typeof observacao !== 'string' || observacao.length > 2000))) {
        return res.status(400).json({ erro: 'Identificador ou observação inválidos' });
    }
    next();
}
module.exports = { validarCriacao, validarDecisao };

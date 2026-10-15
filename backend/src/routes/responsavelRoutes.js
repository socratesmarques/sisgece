const express = require('express');

const {
    buscarPorCpf
} = require('../controllers/responsavelController');

const router = express.Router();

router.get('/:cpf', buscarPorCpf);

module.exports = router;